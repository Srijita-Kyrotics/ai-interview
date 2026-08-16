import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Clock,
  Code2,
  ListChecks,
  Loader2,
  MessageSquare,
  Mic,
  Send,
  Volume2,
  XCircle,
} from 'lucide-react';
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring';
import { ProctoringModal } from '../proctoring/ProctoringUI';
import ObiAvatar from './ObiAvatar';
import { clearStoredUser } from '../api';
import { ROLE_MAPPINGS } from '../constants';
import {
  FinalReportView,
  LiveStatusPill,
  MessageBubble,
  ProgressBar,
  ThinkingIndicator,
  WaveformVisualizer,
} from './aiInterviewer/parts';
import StartCard from './aiInterviewer/StartCard';
import CodingPanel from './aiInterviewer/CodingPanel';

const API_BASE = import.meta.env.VITE_API_URL || '/api';
const getWsBase = () =>
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api`;

// Obi asks at most MAX_QUESTIONS questions (follow-ups count toward the cap).
// The estimate assumes ~2.5 minutes per question including reading + answering.
const DEFAULT_ROLE = 'Software Engineer';
const MAX_QUESTIONS = 12;
const MINUTES_PER_QUESTION = 3.5;
const ESTIMATED_MINUTES = Math.round((MAX_QUESTIONS * MINUTES_PER_QUESTION) / 5) * 5;

// Browser TTS is the fallback when the backend streams no audio chunks.
const BROWSER_TTS_FALLBACK = true;

const LANGUAGE_OPTIONS = [
  { key: 'python', label: 'Python' },
  { key: 'javascript', label: 'JavaScript' },
  { key: 'java', label: 'Java' },
  { key: 'cpp', label: 'C++' },
];

// Infer the target role from resume skills so a different resume automatically
// targets a different role. Mirrors the scoring used on the company page.
function inferRoleFromResume(resume) {
  const skills = (resume && resume.skills) || [];
  if (!skills.length) return null;
  const userSkills = skills.map((s) => String(s).toLowerCase());
  let bestRole = null;
  let bestScore = 0;
  Object.entries(ROLE_MAPPINGS).forEach(([roleName, meta]) => {
    const matched = meta.keywords.filter((kw) =>
      userSkills.some((us) => us.includes(kw))
    );
    if (matched.length > bestScore) {
      bestScore = matched.length;
      bestRole = roleName;
    }
  });
  return bestRole;
}

export default function AIInterviewer({ sessionId, token, role, company, resume, onComplete, proctoring, setProctoring }) {
  const navigate = useNavigate();

  // ── State ───────────────────────────────────────────────────────────
  const [phase, setPhase] = useState('idle');
  // idle → initializing → opening → interviewing → completing → completed | error

  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Preparing your interview...');
  const [subtitleText, setSubtitleText] = useState('');
  const [lipLevel, setLipLevel] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const lipSyncIntervalRef = useRef(null);
  const audioMonitorRef = useRef(null);

  const interviewHighlights = [
    { label: 'Resume', value: resume ? 'Reviewed' : 'Ready' },
    { label: 'Flow', value: 'Adaptive' },
    { label: 'Format', value: 'Voice + Code' },
  ];

  const [interviewSessionId, setInterviewSessionId] = useState(null);
  const [progress, setProgress] = useState({ current: 1, total: 1 });
  const [currentStage, setCurrentStage] = useState('');
  const [finalReport, setFinalReport] = useState(null);
  const [error, setError] = useState(null);
  const [resumableSession, setResumableSession] = useState(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [resumeSummaryOpen, setResumeSummaryOpen] = useState(false);
  const [resumeText, setResumeText] = useState('');
  const [resumeFile, setResumeFile] = useState(null);
  const [uploadedSessionId, setUploadedSessionId] = useState(null);
  const [uploadedResume, setUploadedResume] = useState(null);
  const [uploadingResume, setUploadingResume] = useState(false);
  const [resumeUploadError, setResumeUploadError] = useState('');
  const resumeFileInputRef = useRef(null);

  // ── Code Editor State ──────────────────────────────────────────────
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [activeTab, setActiveTab] = useState('chat');
  const [stdin, setStdin] = useState('');
  const [runOutput, setRunOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [testResults, setTestResults] = useState(null);
  const [isTesting, setIsTesting] = useState(false);
  const [codingProblem, setCodingProblem] = useState(null);
  const languageRef = useRef('python');
  useEffect(() => { languageRef.current = language; }, [language]);
  const codeRef = useRef('');
  useEffect(() => { codeRef.current = code; }, [code]);

  const formatElapsed = (sec) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  // Elapsed timer while interviewing
  useEffect(() => {
    if (phase !== 'interviewing') return;
    setElapsedSec(0);
    const t = setInterval(() => setElapsedSec(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // ── Proctoring State ────────────────────────────────────────────────
  const videoRef = useRef(null);
  const userStreamRef = useRef(null);
  const [userStream, setUserStream] = useState(null);

  // Camera-based video proctoring is enabled for the Obi round. The camera is
  // optional (requested gracefully): if it is denied, tab-switch / fullscreen /
  // devtools checks still run and face detection simply stays off.
  const proctoringEnabled = true;

  // The proctoring hook terminates the interview on the 3rd warning. Route
  // that through phase so the UI stops, the WS closes and we never keep
  // recording after the assessment ended.
  const handleProctorSetState = useCallback((updater) => {
    setPhase((currentPhase) => {
      const next = typeof updater === 'function' ? updater({ stage: currentPhase }) : updater;
      if (next && next.stage === 'terminated') {
        try {
          if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
          }
        } catch (err) { /* ignore */ }
        try { speechRecognitionRef.current?.stop(); } catch (err) { /* ignore */ }
        try { wsRef.current?.close(); } catch (err) { /* ignore */ }
      }
      return next && next.stage === 'terminated' ? 'terminated' : currentPhase;
    });
  }, []);

  const requestCameraPermission = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) return null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      userStreamRef.current = stream;
      setUserStream(stream);
      return stream;
    } catch (err) {
      console.warn('[AIInterviewer] Camera unavailable — proctoring runs without face detection.', err);
      return null;
    }
  }, []);

  const stopCamera = useCallback(() => {
    const stream = userStreamRef.current;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    userStreamRef.current = null;
    setUserStream(null);
  }, []);

  const proctor = useAssessmentProctoring({
    active: proctoringEnabled && (
      phase === 'interviewing' || phase === 'opening' || phase === 'initializing'
    ),
    round: 'technical',
    sessionId,
    navigate,
    setState: handleProctorSetState,
    proctoring,
    setProctoring,
    webcamVideoRef: videoRef,
    webcamStream: userStream,
    screenStream: null,
    voiceInterview: true
  });

  // Feed the webcam stream into the hidden proctoring video element.
  useEffect(() => {
    const video = videoRef.current;
    if (video && userStream) {
      video.srcObject = userStream;
      video.play?.().catch(() => {
        // Muted inline playback is normally automatic; a failed play simply
        // leaves camera-based detection on standby rather than blocking Obi.
      });
    }
    return () => {
      if (video) video.srcObject = null;
    };
  }, [userStream]);

  // The webcam belongs only to the live interview. Stop it immediately once
  // Obi finishes, fails to start, or proctoring terminates the session.
  useEffect(() => {
    if (phase === 'completed' || phase === 'error' || phase === 'terminated') {
      stopCamera();
    }
  }, [phase, stopCamera]);

  const phaseRef = useRef(phase);
  const reconnectAttemptsRef = useRef(reconnectAttempts);
  const audioAwaitingRef = useRef(false);
  const fallbackTtsTimeoutRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const tokenRefreshRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textInputRef = useRef(null);
  const speechRecognitionRef = useRef(null);
  const browserTranscriptRef = useRef('');
  const pendingAudioRef = useRef(null);
  const audioEndSentRef = useRef(false);
  const audioEndTimerRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingAudioRef = useRef(false);

  useEffect(() => { phaseRef.current = phase }, [phase]);
  useEffect(() => { reconnectAttemptsRef.current = reconnectAttempts }, [reconnectAttempts]);

  const requestMicPermission = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      return false;
    }

    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      return true;
    } catch (err) {
      setError('Microphone access is required to continue. Please enable microphone permissions and refresh the page.');
      setPhase('error');
      return false;
    }
  }, []);

  const clearAudioFallbackTimer = useCallback(() => {
    if (fallbackTtsTimeoutRef.current) {
      clearTimeout(fallbackTtsTimeoutRef.current);
      fallbackTtsTimeoutRef.current = null;
    }
  }, []);

  const clearLipSync = useCallback(() => {
    if (lipSyncIntervalRef.current) {
      clearInterval(lipSyncIntervalRef.current);
      lipSyncIntervalRef.current = null;
    }
    setLipLevel(0);
  }, []);

  const startLipSync = useCallback(() => {
    clearLipSync();
    setLipLevel(0.3);
    lipSyncIntervalRef.current = setInterval(() => {
      setLipLevel(0.25 + Math.random() * 0.5);
    }, 70);
  }, [clearLipSync]);

  // ── Real-audio level monitor ──────────────────────────────────────────
  // When the backend sends TTS audio we attach an AnalyserNode so the
  // avatar mouth + waveform move with the actual audio being played
  // (this replaces the random lip-sync during real TTS playback).
  const stopAudioLevelMonitor = useCallback(() => {
    if (audioMonitorRef.current) {
      cancelAnimationFrame(audioMonitorRef.current);
      audioMonitorRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  const startAudioLevelMonitor = useCallback((analyser) => {
    stopAudioLevelMonitor();
    const data = new Uint8Array(analyser.frequencyBinCount);
    let last = 0;
    const tick = () => {
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) sum += data[i];
      const avg = sum / data.length / 255;
      const smoothed = last + (avg - last) * 0.4;
      last = smoothed;
      setAudioLevel(smoothed);
      setLipLevel(0.18 + Math.min(smoothed * 3.2, 0.9));
      audioMonitorRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, [stopAudioLevelMonitor]);

  useEffect(() => {
    const checkResumable = async () => {
      if (!sessionId || !token) return;
      try {
        const res = await fetch(`${API_BASE}/ai-interview/start`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            session_id: sessionId,
            role: inferRoleFromResume(resume) || role || DEFAULT_ROLE,
            company: company || 'the company',
            max_questions: MAX_QUESTIONS,
            voice_enabled: true,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.status === 'resumable') {
            setResumableSession(data.interview_session_id);
          }
        }
      } catch {
        // Ignore — will start fresh
      }
    };
    checkResumable();
  }, [sessionId, token, role, company, resume]);

  // ── Token Refresh ───────────────────────────────────────────────────
  const refreshToken = useCallback(async () => {
    if (!interviewSessionId || !token) return;
    try {
      const res = await fetch(`${API_BASE}/ai-interview/refresh-token?interview_session_id=${interviewSessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        // Send new token to WebSocket
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'refresh_token',
            token: data.token,
          }));
        }
      }
    } catch {
      // Token refresh failed — will reconnect on next disconnect
    }
  }, [interviewSessionId, token]);

  // Start token refresh interval (every 20 minutes for 24h expiry)
  useEffect(() => {
    if (phase === 'interviewing' || phase === 'opening') {
      tokenRefreshRef.current = setInterval(refreshToken, 20 * 60 * 1000);
      return () => clearInterval(tokenRefreshRef.current);
    }
  }, [phase, refreshToken]);

  // ── Finalize AI Response ──────────────────────────────────────────────
  const finishAiResponse = useCallback(() => {
    setIsThinking(false);
    setIsProcessing(false);
    audioAwaitingRef.current = false;
  }, []);

  // ── Speech Synthesis Helper for Obi ─────────────────────────────────
  const pickNaturalVoice = useCallback(() => {
    if (!('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    const natural = voices.find(v => /Google US English|Microsoft (Aria|Jenny|Guy|Ava) Natural/i.test(v.name));
    if (natural) return natural;
    const en = voices.find(v => /en[-_]US/i.test(v.lang) && /Samantha|Daniel|Karen/i.test(v.name));
    if (en) return en;
    return voices.find(v => /en/i.test(v.lang)) || null;
  }, []);

  const speakText = useCallback((text) => {
    if (!('speechSynthesis' in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const cleanText = text.replace(/[*#_`]/g, ''); // Strip markdown
      const utterance = new SpeechSynthesisUtterance(cleanText);
      const voice = pickNaturalVoice();
      if (voice) utterance.voice = voice;
      utterance.lang = 'en-US';
      utterance.rate = 0.95;
      utterance.pitch = 1.05;
      setSubtitleText(cleanText);
      setIsSpeaking(true);
      startLipSync();
      utterance.onend = () => {
        stopAudioLevelMonitor();
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      utterance.onerror = () => {
        stopAudioLevelMonitor();
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
    }
  }, [finishAiResponse, startLipSync, clearLipSync, stopAudioLevelMonitor, pickNaturalVoice]);

  const addMessage = (msg) => {
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), ...msg }]);
  };

  const queueAiMessage = useCallback((message, options = {}) => {
    stopAudioLevelMonitor();
    setIsThinking(false);
    setIsSpeaking(false);
    setIsProcessing(false);
    setStatusMessage(options.status || 'Obi is speaking...');
    setSubtitleText(message || '');
    audioAwaitingRef.current = true;

    if (options.phase) {
      setPhase(options.phase);
    }

    clearAudioFallbackTimer();
    fallbackTtsTimeoutRef.current = setTimeout(() => {
      if (!audioAwaitingRef.current && BROWSER_TTS_FALLBACK) return;
      if ('speechSynthesis' in window && message) {
        speakText(message);
      }
    }, 4000);
  }, [clearAudioFallbackTimer, speakText, stopAudioLevelMonitor]);

  // Role is derived from the uploaded (or pre-loaded) resume via ROLE_MAPPINGS,
  // so uploading a different resume changes the target role automatically.
  const effectiveRole = useMemo(() => {
    return inferRoleFromResume(uploadedResume || resume) || role || DEFAULT_ROLE;
  }, [uploadedResume, resume, role]);

  const openingIntro = `Hi, I'm Obi, your AI interviewer. I've reviewed your resume and I'm tailoring the conversation to your background in ${effectiveRole || DEFAULT_ROLE}. We’ll start with your experience, dig into your projects, and then test your technical depth.`;

  // ── WebSocket Message Handler ────────────────────────────────────────
  const handleWsMessage = useCallback((msg) => {
    const { type } = msg;

    switch (type) {
      case 'thinking':
        setIsThinking(true);
        setIsProcessing(false);
        break;

      case 'processing':
        setIsProcessing(true);
        setIsThinking(false);
        setIsSpeaking(false);
        setStatusMessage('Transcribing your response…');
        break;

      case 'status':
        if (msg.message) {
          setStatusMessage(msg.message);
        }
        break;

      case 'session_ready':
        setPhase('interviewing');
        setIsThinking(false);
        setIsProcessing(false);
        queueAiMessage(msg.opening_text || openingIntro, {
          status: 'Obi is joining the interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'session_restored': {
        setPhase('interviewing');
        setIsThinking(false);
        setProgress({
          current: (msg.stage_index ?? 0) + 1,
          total: msg.total_stages || 1,
        });
        setCurrentStage(msg.current_stage || '');
        const restoredProgress = msg.main_questions_asked ?? msg.questions_asked ?? 0;
        const restoreMsg = `Session restored. Continuing from question ${restoredProgress}...`;
        queueAiMessage(restoreMsg, {
          status: 'Resuming your interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;
      }

      case 'question':
        setIsThinking(false);
        setPhase('interviewing');
        setCurrentStage(msg.stage || '');
        if (msg.stage_index !== undefined) {
          setProgress({
            current: msg.stage_index + 1,
            total: msg.total_stages || 1,
          });
        }
        queueAiMessage(msg.text, {
          status: 'Obi is asking the next question…',
          phase: 'interviewing',
          isFollowUp: msg.is_follow_up,
        });
        break;

      case 'transition':
        setIsThinking(false);
        queueAiMessage(msg.text, {
          status: 'Obi is updating the interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'coding_problem': {
        if (msg.problem) {
          setCodingProblem(msg.problem);
          setActiveTab('code');
          // Pre-fill starter code for the current language if the editor is empty
          const lang = languageRef.current;
          setCode(prev => {
            if (prev && prev.trim()) return prev;
            const starter = msg.problem.starter_code || {};
            return starter[lang] || '';
          });
        }
        break;
      }

      case 'interview_complete':
        setIsThinking(false);
        setPhase('completing');
        if (msg.closing_text) {
          addMessage({ role: 'interviewer', text: msg.closing_text, ts: Date.now() / 1000 });
          speakText(msg.closing_text);
        }
        setTimeout(() => {
          setPhase('completed');
          setFinalReport(msg.report || null);
          if (onComplete) onComplete(msg.report);
        }, 2000);
        break;

      case 'stt_result':
        setIsProcessing(false);
        if (msg.is_final && msg.text) {
          addMessage({ role: 'candidate', text: msg.text, ts: Date.now() / 1000 });
          setStatusMessage('Obi is thinking about your answer…');
        }
        break;

      case 'ai_response_text':
        queueAiMessage(msg.text, {
          status: 'Obi is speaking…',
          phase: 'interviewing',
        });
        break;

      case 'error':
        setIsThinking(false);
        setError(msg.message);
        break;

      case 'pong':
        break;

      default:
        console.log('[AIInterviewer] Unknown message type:', type, msg);
    }
  }, [queueAiMessage, speakText, openingIntro]);

  // ── Serialized Audio Playback Queue ─────────────────────────────────
  // The backend streams TTS as multiple MP3 chunks. Every binary message is
  // queued here and played one at a time so chunks never overlap. The
  // fallback timer / isAwaiting flag only reset once the whole queue drains.
  const playNextAudioChunk = useCallback(() => {
    const queue = audioQueueRef.current;
    if (!queue.length) {
      isPlayingAudioRef.current = false;
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
      return;
    }
    const arrayBuffer = queue.shift();
    const audioCtx = audioContextRef.current || new (window.AudioContext || window.webkitAudioContext)();
    audioContextRef.current = audioCtx;
    audioCtx.decodeAudioData(arrayBuffer).then((audioData) => {
      const source = audioCtx.createBufferSource();
      source.buffer = audioData;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      source.start(0);
      setIsSpeaking(true);
      setIsProcessing(false);
      startAudioLevelMonitor(analyser);
      source.onended = () => {
        if (audioContextRef.current === audioCtx) {
          stopAudioLevelMonitor();
        }
        playNextAudioChunk();
      };
    }).catch((err) => {
      console.error('[AIInterviewer] Audio playback failed', err);
      playNextAudioChunk();
    });
  }, [finishAiResponse, clearLipSync, startAudioLevelMonitor, stopAudioLevelMonitor]);

  const handleAudioResponse = useCallback((arrayBuffer) => {
    clearAudioFallbackTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    audioQueueRef.current.push(arrayBuffer);
    if (!isPlayingAudioRef.current) {
      isPlayingAudioRef.current = true;
      playNextAudioChunk();
    }
  }, [clearAudioFallbackTimer, playNextAudioChunk]);

  // ── Auto-reconnect on disconnect ────────────────────────────────────
  const reconnectWs = useCallback(() => {
    if (!interviewSessionId || !token || !sessionId) return;
    if (reconnectAttempts >= 5) {
      setError('Connection lost. Please refresh the page.');
      setPhase('error');
      return;
    }

    setReconnectAttempts(prev => prev + 1);
    setPhase('opening');

    const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${interviewSessionId}&session_id=${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('[AIInterviewer] WebSocket reconnected');
      setReconnectAttempts(0);
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        handleWsMessage(JSON.parse(event.data));
      } else {
        handleAudioResponse(event.data);
      }
    };

    ws.onerror = () => {
      // Will trigger onclose
    };

    ws.onclose = () => {
      if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
        reconnectTimerRef.current = setTimeout(reconnectWs, 2000 * (reconnectAttempts + 1));
      }
    };
  }, [interviewSessionId, token, sessionId, reconnectAttempts, handleWsMessage, handleAudioResponse]);

  // Cleanup reconnect timer
  useEffect(() => {
    return () => {
      clearTimeout(reconnectTimerRef.current);
      clearInterval(tokenRefreshRef.current);
    };
  }, []);

  // ── Resume File Upload ────────────────────────────────────────────────
  const handleResumeFile = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt'].includes(ext)) {
      setResumeUploadError('Only PDF or TXT files are supported.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setResumeUploadError('File must be under 10 MB.');
      return;
    }

    setUploadingResume(true);
    setResumeUploadError('');
    setResumeFile(file);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${API_BASE}/ai-interview/upload-resume`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        if (res.status === 401) clearStoredUser();
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to parse the resume.');
      }
      const data = await res.json();
      setUploadedSessionId(data.session_id);
      setUploadedResume(data.resume || null);
      setResumeText('');
    } catch (err) {
      setResumeUploadError(err.message || 'Could not parse the resume.');
      setResumeFile(null);
      setUploadedSessionId(null);
      setUploadedResume(null);
    } finally {
      setUploadingResume(false);
    }
  }, [token]);

  const clearUploadedResume = useCallback(() => {
    setResumeFile(null);
    setUploadedSessionId(null);
    setUploadedResume(null);
    setResumeUploadError('');
    if (resumeFileInputRef.current) resumeFileInputRef.current.value = '';
  }, []);

  // ── Start Interview ──────────────────────────────────────────────────
  const startInterview = useCallback(async (resumeExisting = true) => {
    setPhase('initializing');
    setStatusMessage('Preparing your interview...');
    setError(null);

    try {
      const shouldResume = resumeExisting && Boolean(resumableSession);
      let activeSessionId = sessionId;

      if (!shouldResume) {
        const pastedResume = resumeText.trim();
        if (uploadedSessionId) {
          // A resume file was uploaded → use its session directly.
          activeSessionId = uploadedSessionId;
        } else if (pastedResume) {
          // Seed a fresh session with the pasted resume so Obi can
          // personalize questions to the candidate's actual background.
          const createRes = await fetch(`${API_BASE}/ai-interview/create-session`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ resume_text: pastedResume }),
          });
          if (!createRes.ok) {
            throw new Error('Failed to create interview session');
          }
          const createData = await createRes.json();
          activeSessionId = createData.session_id;
        }
      }

      const endpoint = shouldResume ? '/ai-interview/resume' : '/ai-interview/start';
      const url = `${API_BASE}${endpoint}`;
      const body = shouldResume
        ? JSON.stringify({ interview_session_id: resumableSession, session_id: activeSessionId })
        : JSON.stringify({
            session_id: activeSessionId,
            role: effectiveRole,
            company: company || 'the company',
            max_questions: MAX_QUESTIONS,
            voice_enabled: true,
          });
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body,
      });

      if (!res.ok) {
        if (res.status === 401) clearStoredUser();
        throw new Error(`Failed to initialize interview: ${res.statusText}`);
      }

      const data = await res.json();
      const ivSessionId = data.interview_session_id;
      setInterviewSessionId(ivSessionId);
      if (data.status === 'resumable' && !resumableSession) {
        setResumableSession(ivSessionId);
      }

      const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${ivSessionId}&session_id=${activeSessionId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        console.log('[AIInterviewer] WebSocket connected');
        setPhase('opening');
        setStatusMessage('Connecting to Obi...');
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          handleWsMessage(JSON.parse(event.data));
        } else {
          // Binary: TTS audio
          handleAudioResponse(event.data);
        }
      };

      ws.onerror = (e) => {
        console.error('[AIInterviewer] WebSocket error', e);
        setError('Connection error. Please refresh and try again.');
        setPhase('error');
      };

      ws.onclose = () => {
        console.log('[AIInterviewer] WebSocket closed');
        if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
          reconnectTimerRef.current = setTimeout(() => {
            if (wsRef.current === ws) {
              reconnectWs();
            }
          }, 2000);
        }
      };

    } catch (err) {
      console.error('[AIInterviewer] Start failed', err);
      setError(err.message);
      setPhase('error');
    }
  }, [sessionId, token, effectiveRole, company, resumeText, resumableSession, uploadedSessionId]);

  // ── Explicit start (Begin button) ────────────────────────────────────
  // The interview only starts on user action — no surprise mic/camera
  // requests on page load.
  const beginInterview = useCallback(async (resumeExisting = true) => {
    const allowed = await requestMicPermission();
    if (!allowed) {
      setError('Microphone permission is required to start the voice interview.');
      setPhase('idle');
      return;
    }
    await requestCameraPermission(); // optional — never blocks the interview
    startInterview(resumeExisting);
  }, [requestMicPermission, requestCameraPermission, startInterview]);

  // ── Send Text Answer ─────────────────────────────────────────────────
  const sendAnswer = useCallback((text) => {
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    addMessage({ role: 'candidate', text, ts: Date.now() / 1000 });
    setIsThinking(true);

    wsRef.current.send(JSON.stringify({
      type: 'answer',
      text,
      code: code || undefined,
      language: code ? language : undefined,
    }));
  }, [code, language]);

  // ── Run Code ───────────────────────────────────────────────────────
  const runCode = useCallback(async () => {
    if (!code.trim() || isRunning) return;
    setIsRunning(true);
    setRunStatus('Running…');
    setRunOutput('');
    try {
      const res = await fetch(`${API_BASE}/ai-interview/run-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ language, code, stdin }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRunStatus(data.detail || data.message || `Run failed (${res.status})`);
        setRunOutput(data.error || '');
        return;
      }
      if (!data.ok) {
        setRunStatus(data.error || 'Could not run code.');
        return;
      }
      setRunStatus(data.timed_out ? 'Execution timed out.' : 'Ran successfully.');
      const out = [data.stdout, data.stderr].filter(Boolean).join('\n');
      setRunOutput(out || '(no output)');
    } catch (err) {
      setRunStatus('Could not contact run service.');
      setRunOutput(err.message || '');
    } finally {
      setIsRunning(false);
    }
  }, [code, language, stdin, token, isRunning]);

  // ── Run Tests (visible test cases) ───────────────────────────────────
  const runTests = useCallback(async () => {
    const cases = codingProblem?.visible_test_cases || [];
    if (!code.trim() || isRunning || isTesting || cases.length === 0) return;
    setIsTesting(true);
    setTestResults(null);
    try {
      const res = await fetch(`${API_BASE}/ai-interview/judge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ language, code, test_cases: cases }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTestResults({ error: data.detail || data.message || `Judge failed (${res.status})` });
        return;
      }
      setTestResults(data);
    } catch (err) {
      setTestResults({ error: 'Could not contact judge service.' });
    } finally {
      setIsTesting(false);
    }
  }, [code, language, token, codingProblem, isRunning, isTesting]);

  // ── Voice Recording ──────────────────────────────────────────────────
  // Sends `audio_end` with the browser-transcribed text when available, so
  // the backend can skip cloud STT (no API key required). If the browser
  // SpeechRecognition API is unavailable or returns nothing, the raw audio
  // bytes are still sent for the configured STT provider.
  const sendAudioEnd = useCallback((transcript) => {
    if (audioEndSentRef.current) return;
    audioEndSentRef.current = true;
    clearTimeout(audioEndTimerRef.current);
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (pendingAudioRef.current) ws.send(pendingAudioRef.current);
    ws.send(JSON.stringify({
      type: 'audio_end',
      code: codeRef.current || undefined,
      language: codeRef.current ? languageRef.current : undefined,
      transcript: (transcript || browserTranscriptRef.current || '').trim(),
    }));
    setIsThinking(true);
  }, []);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      browserTranscriptRef.current = '';
      audioEndSentRef.current = false;
      pendingAudioRef.current = null;

      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) {
        const recognition = new SR();
        speechRecognitionRef.current = recognition;
        recognition.lang = 'en-US';
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onresult = (event) => {
          const parts = [];
          for (let i = 0; i < event.results.length; i += 1) {
            if (event.results[i].isFinal) parts.push(event.results[i][0].transcript);
          }
          if (parts.length) browserTranscriptRef.current = parts.join(' ').trim();
        };
        recognition.onerror = (event) => {
          console.warn('[AIInterviewer] Browser STT error:', event.error);
        };
        recognition.onend = () => {
          // Only fire once the mic has actually been released.
          if (!audioEndSentRef.current && mediaRecorderRef.current?.state !== 'recording') {
            sendAudioEnd();
          }
        };
      }

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        pendingAudioRef.current = await blob.arrayBuffer();
        const sr = speechRecognitionRef.current;
        if (sr) {
          try { sr.stop(); } catch (err) { /* already stopped */ }
          // Safety net: never block the answer on the browser STT.
          audioEndTimerRef.current = setTimeout(() => {
            if (!audioEndSentRef.current) sendAudioEnd();
          }, 3000);
        } else {
          sendAudioEnd();
        }
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start(250); // collect data every 250ms
      if (speechRecognitionRef.current) {
        try { speechRecognitionRef.current.start(); } catch (err) { /* already started */ }
      }
      setIsRecording(true);
    } catch (err) {
      console.error('[AIInterviewer] Microphone access failed', err);
      setError('Microphone access denied. Please allow mic access and try again.');
    }
  }, [sendAudioEnd]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  // ── End Interview ────────────────────────────────────────────────────
  const endInterview = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_voice' }));
      setIsThinking(true);
      setPhase('completing');
    }
  }, []);

  // ── Keyboard Handler ─────────────────────────────────────────────────
  const submitTypedAnswer = useCallback(() => {
    const input = textInputRef.current;
    const value = input?.value.trim();
    if (!value || isThinking || isSpeaking) return;

    sendAnswer(value);
    if (input) input.value = '';
  }, [isSpeaking, isThinking, sendAnswer]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      submitTypedAnswer();
    }
  };

  // Auto-scroll the transcript to the newest message.
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages, isThinking]);

  // ── Cleanup ──────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      audioContextRef.current?.close();
      clearTimeout(reconnectTimerRef.current);
      clearTimeout(fallbackTtsTimeoutRef.current);
      clearTimeout(audioEndTimerRef.current);
      clearInterval(tokenRefreshRef.current);
      try { speechRecognitionRef.current?.stop(); } catch (err) { /* ignore */ }
      const stream = userStreamRef.current;
      if (stream) stream.getTracks().forEach((track) => track.stop());
      userStreamRef.current = null;
    };
  }, []);

  // ─────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────

  // ── Idle / Start Screen ───────────────────────────────────────────────
  if (phase === 'idle') {
    return (
      <div className="aii-container">
        <StartCard
          effectiveRole={effectiveRole}
          estimatedMinutes={ESTIMATED_MINUTES}
          highlights={interviewHighlights}
          resume={resume}
          resumeFile={resumeFile}
          resumeText={resumeText}
          resumeSummaryOpen={resumeSummaryOpen}
          uploadingResume={uploadingResume}
          resumeUploadError={resumeUploadError}
          resumableSession={resumableSession}
          resumeFileInputRef={resumeFileInputRef}
          onToggleResumeSummary={() => setResumeSummaryOpen((open) => !open)}
          onResumeTextChange={(e) => setResumeText(e.target.value)}
          onResumeFileChange={handleResumeFile}
          onClearResumeFile={clearUploadedResume}
          onBegin={beginInterview}
        />
      </div>
    );
  }

  // ── Error Screen ──────────────────────────────────────────────────────
  if (phase === 'error') {
    return (
      <div className="aii-container">
        <div className="aii-error-card">
          <div className="aii-error-card__icon"><AlertTriangle size="48" /></div>
          <h3>Interview Error</h3>
          <p>{error || 'An unexpected error occurred.'}</p>
          <button className="aii-start-btn" onClick={() => { setPhase('idle'); setError(null); }}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ── Completed: Final Report ────────────────────────────────────────────
  if (phase === 'completed' && finalReport) {
    return <FinalReportView finalReport={finalReport} onComplete={onComplete} />;
  }

  // ── Interview Room ────────────────────────────────────────────────────
  const avatarState = isSpeaking
    ? 'speaking'
    : isThinking || isProcessing
      ? 'thinking'
      : isRecording
        ? 'listening'
        : reconnectAttempts > 0
          ? 'error'
          : phase === 'opening' || phase === 'initializing'
            ? 'connecting'
            : 'idle';

  const stageStatusText =
    phase === 'initializing' || phase === 'opening' ? statusMessage : '';

  return (
    <div className="aii-container aii-container--active aii-room">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />
      {/* Header */}
      <div className="aii-header aii-room__header">
        <div className="aii-header__interviewer">
          <ObiAvatar compact state={avatarState} lipLevel={lipLevel} audioLevel={audioLevel} />
          <div>
            <div className="aii-header__name">Obi</div>
            <div className="aii-header__subrow">
              <span className="aii-header__title">AI Technical Interviewer</span>
              <LiveStatusPill
                isRecording={isRecording}
                isSpeaking={isSpeaking}
                isThinking={isThinking}
                isProcessing={isProcessing}
                isConnecting={phase === 'opening' || phase === 'initializing'}
              />
            </div>
          </div>
        </div>

        <div className="aii-header__controls">
          <div className="aii-header__stats">
            <div className="aii-stat">
              <Clock size="14" />
              <span>Interview · {formatElapsed(elapsedSec)}</span>
            </div>
            <div className="aii-stat">
              <ListChecks size="14" />
              <span>Stage {progress.current}/{progress.total}</span>
            </div>
          </div>
          {currentStage && (
            <div className="aii-stage-badge">{currentStage}</div>
          )}
          <button
            className="aii-end-btn"
            onClick={endInterview}
            disabled={phase !== 'interviewing'}
            title="End Interview"
          >
            <XCircle size="14" /> End Interview
          </button>
        </div>
      </div>

      {/* Progress */}
      {phase === 'interviewing' && (
        <ProgressBar
          current={progress.current}
          total={progress.total}
          stages={{ currentStage }}
        />
      )}

      {/* Interview Room Stage — Obi is the main visual focus */}
      <div className="aii-room__stage">
        <ObiAvatar state={avatarState} lipLevel={lipLevel} audioLevel={audioLevel} statusText={stageStatusText} />
        <div className="aii-subtitle-card">
          <div className="aii-subtitle-card__label"><Volume2 size="12" /> Live subtitle</div>
          <p className="aii-subtitle-card__text">{subtitleText || 'Obi will speak here once the interview begins.'}</p>
        </div>
      </div>

      {/* Session Panel: tabs + chat + code */}
      <div className="aii-room__panel">
        <div className="aii-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === 'chat'}
            className={`aii-tab-btn ${activeTab === 'chat' ? 'aii-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size="14" />
            Chat
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'code'}
            className={`aii-tab-btn ${activeTab === 'code' ? 'aii-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('code')}
          >
            <Code2 size="14" />
            Code
          </button>
        </div>

        {phase === 'initializing' && (
          <div className="aii-init-message">
            <ObiAvatar compact state="connecting" />
            <div className="aii-spinner aii-spinner--sm" />
            <p>{statusMessage || 'Obi is reading your resume and preparing your interview…'}</p>
          </div>
        )}

        <div className={`aii-chat ${activeTab !== 'chat' ? 'aii-chat--hidden' : ''}`}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id || `${msg.role}-${msg.ts}`} message={msg} />
          ))}

          {isThinking && <ThinkingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        {activeTab === 'code' && (
          <CodingPanel
            problem={codingProblem}
            language={language}
            onLanguageChange={setLanguage}
            code={code}
            onCodeChange={setCode}
            stdin={stdin}
            onStdinChange={setStdin}
            runStatus={runStatus}
            runOutput={runOutput}
            isRunning={isRunning}
            isTesting={isTesting}
            isThinking={isThinking}
            testResults={testResults}
            onRun={runCode}
            onTest={runTests}
            onSend={() => {
              const submission = `Here is my code solution in ${language}:\n\`\`\`${language}\n${code}\n\`\`\`\nExecution Output:\n${runOutput || '(Code executed)'}`;
              sendAnswer(submission);
              setActiveTab('chat');
            }}
            languageOptions={LANGUAGE_OPTIONS}
          />
        )}
      </div>

      {/* Input Area */}
      {phase === 'interviewing' && (
        <div className="aii-input-area aii-room__controls">
          <div className="aii-voice-controls">
            <div className="aii-voice-row">
              <div className="aii-mic-wrap">
                <button
                  className={`aii-mic-btn ${isRecording ? 'aii-mic-btn--recording' : ''}`}
                  onMouseDown={startRecording}
                  onMouseUp={stopRecording}
                  onTouchStart={startRecording}
                  onTouchEnd={stopRecording}
                  onMouseLeave={stopRecording}
                  onContextMenu={(e) => e.preventDefault()}
                  disabled={isThinking || isSpeaking}
                  title={isRecording ? 'Release to send voice' : 'Hold to speak to Obi'}
                  aria-label={isRecording ? 'Release to send voice' : 'Hold to speak to Obi'}
                >
                  <Mic size="26" />
                </button>
                <span className="aii-mic-label">{isRecording ? 'Release to send' : 'Hold to talk'}</span>
              </div>

              <div className="aii-voice-meta">
                <WaveformVisualizer isActive={isRecording || isSpeaking} color={isRecording ? '#f87171' : '#818cf8'} />
                <div className={`aii-voice-status aii-voice-status--${isRecording ? 'rec' : isSpeaking ? 'speak' : isThinking ? 'think' : 'idle'}`}>
                  {isRecording
                    ? <><span className="aii-voice-status__dot" /> Recording — release to send</>
                    : isSpeaking
                      ? <><Volume2 size="15" /> Obi is speaking</>
                      : isThinking
                        ? <><Loader2 size="15" className="aii-spin" /> Obi is thinking…</>
                        : <><Mic size="15" /> Ready — hold the mic button to answer</>}
                </div>
              </div>
            </div>

            {/* Camera preview — also used by proctoring face/object detection */}
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              aria-hidden="true"
              style={{
                position: 'fixed',
                top: 16,
                right: 16,
                width: 160,
                height: 120,
                borderRadius: 12,
                border: '2px solid rgba(129,140,248,0.4)',
                objectFit: 'cover',
                zIndex: 50,
                transform: 'scaleX(-1)',
                opacity: 0.85,
                boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
              }}
            />

            <div className="aii-text-row">
              <input
                ref={textInputRef}
                type="text"
                className="aii-text-input"
                placeholder="Or type your response to Obi…"
                onKeyDown={handleKeyDown}
                disabled={isThinking || isSpeaking}
                aria-label="Type your response"
              />
              <button
                className="aii-send-btn"
                onClick={submitTypedAnswer}
                disabled={isThinking || isSpeaking}
                title="Send message"
                aria-label="Send message"
              >
                <Send size="18" />
              </button>
            </div>
          </div>
        </div>
      )}

      {phase === 'completing' && (
        <div className="aii-completing">
          <ObiAvatar compact state="thinking" />
          <div className="aii-spinner aii-spinner--sm" />
          <p>Generating your interview report…</p>
        </div>
      )}
    </div>
  );
}
