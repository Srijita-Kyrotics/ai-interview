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
  RotateCcw,
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
  CandidateWebcamCard,
  FinalReportView,
  LiveStatusPill,
  MessageBubble,
  ProgressBar,
  ThinkingIndicator,
  WaveformVisualizer,
} from './aiInterviewer/parts';
import StartCard from './aiInterviewer/StartCard';
import CodingPanel from './aiInterviewer/CodingPanel';

let rawApiBase = import.meta.env.VITE_API_URL || '/api';
const API_BASE = rawApiBase.replace(/\/+$/, '');
const getWsBase = () => {
  let url = import.meta.env.VITE_WS_URL || import.meta.env.VITE_API_URL || '';
  if (url) {
    url = url.replace(/^http:\/\//i, 'ws://').replace(/^https:\/\//i, 'wss://').replace(/\/+$/, '');
    return url;
  }
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api`;
};
const supportsBrowserTts = () => 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

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
  { key: 'c', label: 'C' },
  { key: 'csharp', label: 'C#' },
  { key: 'go', label: 'Go' },
  { key: 'rust', label: 'Rust' },
  { key: 'typescript', label: 'TypeScript' },
];

const DEFAULT_STARTER_CODES = {
  python: '# Write your solution here\ndef solution():\n    pass\n\nprint("Code runner ready.")\n',
  javascript: '// Write your solution here\nfunction solution() {\n  \n}\n\nconsole.log("Code runner ready.");\n',
  java: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Code runner ready.");\n    }\n}\n',
  cpp: '#include <iostream>\nusing namespace std;\n\nint main() {\n    cout << "Code runner ready." << endl;\n    return 0;\n}\n',
  c: '#include <stdio.h>\n\nint main() {\n    printf("Code runner ready.\\n");\n    return 0;\n}\n',
  csharp: 'using System;\n\nclass Program {\n    static void Main() {\n        Console.WriteLine("Code runner ready.");\n    }\n}\n',
  go: 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Code runner ready.")\n}\n',
  rust: 'fn main() {\n    println!("Code runner ready.");\n}\n',
  typescript: '// Write your solution here\nfunction solution(): void {\n  console.log("Code runner ready.");\n}\n\nsolution();\n',
};

const DEFAULT_DIRECT_PROBLEM = {
  id: 'demo-two-sum',
  title: 'Two Sum',
  topic: 'Arrays & Hashing',
  difficulty: 'easy',
  description: 'Given an integer array and a target, return the indices of two values that add up to the target.',
  starter_code: {
    python: 'import sys\n\nnums = list(map(int, sys.stdin.readline().split()))\ntarget = int(sys.stdin.readline())\n\n# Write your solution here\nprint("0 1")\n',
    javascript: 'const fs = require("fs");\nconst lines = fs.readFileSync(0, "utf8").trim().split(/\\r?\\n/);\nconst nums = lines[0].split(/\\s+/).map(Number);\nconst target = Number(lines[1]);\n\n// Write your solution here\nconsole.log("0 1");\n',
  },
  visible_test_cases: [
    { input: '2 7 11 15\n9', expected_output: '0 1' },
    { input: '3 2 4\n6', expected_output: '1 2' },
  ],
};

function normalizeDirectProblem(problem) {
  if (!problem) return DEFAULT_DIRECT_PROBLEM;
  const testCases = problem.visible_test_cases || problem.testCases || [];
  const starterCode = problem.starter_code || problem.starter || {};
  return {
    ...problem,
    id: problem.id ?? `direct-${problem.title || 'problem'}`,
    title: problem.title || 'Coding Challenge',
    topic: problem.topic || 'Algorithms',
    difficulty: problem.difficulty || 'medium',
    description: problem.description || problem.statement || '',
    starter_code: starterCode,
    visible_test_cases: testCases.map((test) => ({
      input: test.input || '',
      expected_output: test.expected_output ?? test.expected ?? '',
    })),
  };
}


// Infer the target role from resume skills, experience, summary, and title.
function inferRoleFromResume(resume) {
  if (!resume) return null;
  const fullText = [
    resume.title,
    ...(resume.skills || []),
    resume.summary,
    resume.text,
    resume.raw_text,
    ...(resume.parsed?.experience || []).map(e => `${e.position || e.title} ${e.company || e.organization}`),
    ...(resume.experience_entries || []).map(e => `${e.role} ${e.company} ${e.key_claims?.join(' ')}`)
  ].filter(Boolean).join(' ').toLowerCase();

  if (!fullText.trim()) return null;

  let bestRole = null;
  let bestScore = 0;
  Object.entries(ROLE_MAPPINGS).forEach(([roleName, meta]) => {
    const matched = meta.keywords.filter((kw) => fullText.includes(kw.toLowerCase()));
    if (matched.length > bestScore) {
      bestScore = matched.length;
      bestRole = roleName;
    }
  });
  return bestRole;
}

export default function AIInterviewer({ sessionId, token, role, company, resume, codingQuestions = [], onComplete, proctoring, setProctoring, proctoringEnabled = true }) {
  const navigate = useNavigate();

  // ── State ───────────────────────────────────────────────────────────
  const [phase, setPhase] = useState('idle');
  // idle → initializing → opening → interviewing → completing → completed | error

  const [messages, setMessages] = useState([]);
  const messagesRef = useRef([]);
  const candidateTurnStartRef = useRef(null);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const [isThinking, setIsThinking] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Preparing your interview...');
  const [subtitleText, setSubtitleText] = useState('');
  const [activeQuestionId, setActiveQuestionId] = useState(null);
  const activeQuestionIdRef = useRef(null);
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
  const [selectedRole, setSelectedRole] = useState(null);
  const [showCodeEditor, setShowCodeEditor] = useState(false);
  const [isDirectCodeMode, setIsDirectCodeMode] = useState(false);
  const [codingEnabled, setCodingEnabled] = useState(() => {
    if (!selectedRole) return true;
    return ROLE_MAPPINGS[selectedRole]?.technical !== false;
  });
  const [stdin, setStdin] = useState('');
  const [runOutput, setRunOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [testResults, setTestResults] = useState(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [codingProblem, setCodingProblem] = useState(null);
  const [submissionResult, setSubmissionResult] = useState(null);
  const [directQuestionIndex, setDirectQuestionIndex] = useState(0);
  const languageRef = useRef('python');
  useEffect(() => { languageRef.current = language; }, [language]);
  const codeRef = useRef('');
  useEffect(() => { codeRef.current = code; }, [code]);

  useEffect(() => {
    if (selectedRole) {
      const isTech = ROLE_MAPPINGS[selectedRole]?.technical !== false;
      setCodingEnabled(isTech);
      if (!isTech) setShowCodeEditor(false);
    }
  }, [selectedRole]);

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
  const isProctoringEnabled = proctoringEnabled;

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
    active: isProctoringEnabled && !isDirectCodeMode && (
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

  // Feed the webcam stream into the proctoring video element.
  useEffect(() => {
    const video = videoRef.current;
    if (video && userStream) {
      if (video.srcObject !== userStream) {
        video.srcObject = userStream;
      }
      video.play?.().catch(() => {
        // Muted inline playback is normally automatic
      });
    }
  }, [userStream, phase]);

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
  const startInProgressRef = useRef(false);
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
  const pendingQuestionTextRef = useRef(null);

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
      console.warn('[AIInterviewer] Microphone unavailable; typed chat remains enabled.', err);
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
    setActiveSubtitleId(null);
  }, []);

  const speechQueueRef = useRef([]);
  const isSpeakingSpeechRef = useRef(false);
  // Questions may arrive while Jack is still reading a greeting or transition.
  // Keep them out of the transcript until the current spoken message ends.
  const pendingQuestionEventsRef = useRef([]);
  const presentQuestionRef = useRef(null);

  const flushPendingQuestion = useCallback(() => {
    if (!presentQuestionRef.current || pendingQuestionEventsRef.current.length === 0) return false;
    presentQuestionRef.current(pendingQuestionEventsRef.current.shift());
    return true;
  }, []);

  // ── Speech Synthesis Helper for Jack (Male Voice) ─────────────────────
  const pickNaturalVoice = useCallback(() => {
    if (!('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    // Prefer professional male voices (Guy, David, George, Mark, Male, Daniel, Christopher)
    const maleVoice = voices.find(v => /Guy|David|George|Mark|Daniel|Male|Christopher/i.test(v.name));
    if (maleVoice) return maleVoice;
    return voices.find(v => /en/i.test(v.lang)) || null;
  }, []);

  const processSpeechQueue = useCallback(() => {
    if (isPlayingAudioRef.current) return;
    if (speechQueueRef.current.length === 0) {
      isSpeakingSpeechRef.current = false;
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
      if (flushPendingQuestion()) return;
      setStatusMessage('Jack is ready');
      return;
    }

    if (isSpeakingSpeechRef.current) return;

    const nextItem = speechQueueRef.current.shift();
    if (!nextItem || !nextItem.text) {
      processSpeechQueue();
      return;
    }

    const cleanText = nextItem.text.replace(/[*#_`]/g, '');
    setSubtitleText(cleanText);
    setStatusMessage(nextItem.status || 'Jack is speaking…');
    setIsSpeaking(true);
    isSpeakingSpeechRef.current = true;
    startLipSync();

    if ('speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(cleanText);
        const voice = pickNaturalVoice();
        if (voice) utterance.voice = voice;
        utterance.lang = 'en-US';
        utterance.rate = 0.95;
        utterance.pitch = 0.95;

        utterance.onend = () => {
          isSpeakingSpeechRef.current = false;
          processSpeechQueue();
        };
        utterance.onerror = () => {
          isSpeakingSpeechRef.current = false;
          processSpeechQueue();
        };

        window.speechSynthesis.speak(utterance);
      } catch {
        isSpeakingSpeechRef.current = false;
        processSpeechQueue();
      }
    } else {
      isSpeakingSpeechRef.current = false;
      processSpeechQueue();
    }
  }, [finishAiResponse, startLipSync, clearLipSync, stopAudioLevelMonitor, pickNaturalVoice, flushPendingQuestion]);

  const queueSpeech = useCallback((text, options = {}) => {
    if (!text || !text.trim()) return;
    speechQueueRef.current.push({ text: text.trim(), ...options });
    if (!isSpeakingSpeechRef.current && !isPlayingAudioRef.current) {
      processSpeechQueue();
    }
  }, [processSpeechQueue]);

  const speakText = useCallback((text) => {
    if (!text) return;
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    isSpeakingSpeechRef.current = false;
    speechQueueRef.current = [{ text, status: 'Jack is speaking…' }];
    processSpeechQueue();
  }, [processSpeechQueue]);

  const addMessage = (msg) => {
    const text = typeof msg?.text === 'string' ? msg.text.trim() : '';
    if (!text) return;
    setMessages(prev => {
      const recent = prev.slice(-6);
      const duplicate = recent.some(existing => existing.role === msg.role && String(existing.text).trim() === text);
      if (duplicate) return prev;
      return [...prev, { id: Date.now() + Math.random(), ...msg }];
    });
  };

  const addCandidateMessage = useCallback((text) => {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();
    setMessages((prev) => {
      const recent = prev.slice(-6);
      const duplicate = recent.some(msg => msg.role === 'candidate' && String(msg.text).trim() === cleanText);
      if (duplicate) return prev;
      const candidateMessage = { id: Date.now() + Math.random(), role: 'candidate', text: cleanText, ts: Date.now() / 1000 };
      const insertionIndex = candidateTurnStartRef.current;
      candidateTurnStartRef.current = null;
      if (insertionIndex === null) return [...prev, candidateMessage];
      const next = [...prev];
      next.splice(Math.min(insertionIndex, next.length), 0, candidateMessage);
      return next;
    });
  }, []);

  const [activeSubtitleId, setActiveSubtitleId] = useState(null);

  const queueAiMessage = useCallback((message, options = {}) => {
    stopAudioLevelMonitor();
    setIsThinking(false);
    setIsProcessing(false);
    setStatusMessage(options.status || 'Jack is speaking…');

    if (message && message.trim()) {
      const cleanText = message.trim();
      const newId = Date.now() + Math.random();
      setActiveSubtitleId(newId);
      setMessages((prev) => {
        const recent = prev.slice(-6);
        const duplicate = recent.some(msg => msg.role === 'interviewer' && String(msg.text).trim() === cleanText);
        if (duplicate) return prev;
        return [...prev, {
          id: newId,
          role: 'interviewer',
          text: cleanText,
          ts: Date.now() / 1000,
          isFollowUp: options.isFollowUp,
          isTransition: options.isTransition,
        }];
      });

      queueSpeech(cleanText, { status: options.status || 'Jack is speaking…' });
    }

    if (options.phase) {
      setPhase(options.phase);
    }
  }, [queueSpeech, stopAudioLevelMonitor]);

  // Role is derived from user selection or resume inference via ROLE_MAPPINGS.
  const effectiveRole = useMemo(() => {
    if (selectedRole) return selectedRole;
    return inferRoleFromResume(uploadedResume || resume) || role || DEFAULT_ROLE;
  }, [selectedRole, uploadedResume, resume, role]);

  const candidateFirstName = useMemo(() => {
    const rawName = (uploadedResume?.name || resume?.name || '').trim();
    if (!rawName) return 'there';
    return rawName.split(' ')[0];
  }, [uploadedResume, resume]);

  const openingIntro = `Hi ${candidateFirstName}, I'm Jack, your interviewer. I've reviewed your resume and I'm tailoring the conversation to your background in ${effectiveRole || DEFAULT_ROLE}. We’ll start with your experience, dig into your projects, and then test your technical depth.`;

  // ── WebSocket Message Handler ────────────────────────────────────────
  const presentQuestion = useCallback((msg) => {
    setIsThinking(false);
    setPhase('interviewing');
    setCurrentStage(msg.stage || '');
    if (msg.stage_index !== undefined) {
      setProgress({ current: msg.stage_index + 1, total: msg.total_stages || 1 });
    }

    const isCodingQuestion = (msg.stage || '').toLowerCase().includes('coding') ||
      (msg.text || '').toLowerCase().includes('coding problem') ||
      (msg.text || '').toLowerCase().includes('please solve');
    if (codingEnabled && isCodingQuestion) {
      setShowCodeEditor(true);
      const lang = languageRef.current || 'python';
      setCode(prev => prev && prev.trim() ? prev : (DEFAULT_STARTER_CODES[lang] || ''));
      setCodingProblem((prev) => {
        if (prev && prev.description) return prev;
        const lines = (msg.text || '').split('\n').map(line => line.trim()).filter(Boolean);
        const titleMatch = (lines[0] || '').match(/coding problem:\s*(.+)$/i);
        return {
          id: 'coding-auto',
          title: titleMatch ? titleMatch[1].trim() : 'Live Coding Challenge',
          difficulty: 'medium',
          topic: 'algorithms',
          description: lines.length > 1 ? lines.slice(1).join('\n\n') : msg.text,
          starter_code: DEFAULT_STARTER_CODES,
          visible_test_cases: [],
        };
      });
    }

    queueAiMessage(msg.text, {
      status: msg.is_follow_up ? 'Jack is asking a follow-up…' : 'Jack is asking the next question…',
      phase: 'interviewing',
      isFollowUp: msg.is_follow_up,
    });
  }, [codingEnabled, queueAiMessage]);

  useEffect(() => {
    presentQuestionRef.current = presentQuestion;
  }, [presentQuestion]);

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

      case 'progress':
        // The voice endpoint emits progress while the resume and first
        // question are being generated.  Previously these events were
        // ignored, leaving the misleading "Jack is ready" status during a
        // potentially long LLM request.
        setIsThinking(true);
        setIsProcessing(false);
        setStatusMessage(msg.step || msg.message || 'Jack is preparing your next question…');
        break;

      case 'session_ready': {
        setPhase('interviewing');
        setIsThinking(false);
        setIsProcessing(false);
        if (msg.coding_enabled === false) {
          setCodingEnabled(false);
          setShowCodeEditor(false);
        } else {
          setCodingEnabled(true);
        }
        const opening = msg.opening_text || openingIntro;
        queueAiMessage(opening, {
          status: 'Jack is introducing the interview…',
          phase: 'interviewing',
        });
        break;
      }

      case 'session_restored': {
        setPhase('interviewing');
        setIsThinking(false);
        setProgress({
          current: (msg.stage_index ?? 0) + 1,
          total: msg.total_stages || 1,
        });
        setCurrentStage(msg.current_stage || '');
        if (msg.coding_enabled === false) {
          setCodingEnabled(false);
          setShowCodeEditor(false);
        } else {
          setCodingEnabled(true);
        }
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
        if (msg.question_id && msg.question_id === activeQuestionIdRef.current) {
          break;
        }
        if (msg.question_id) {
          activeQuestionIdRef.current = msg.question_id;
          setActiveQuestionId(msg.question_id);
        }
        // Show the question as soon as it arrives. Speech remains serialized
        // by queueSpeech(), so the greeting and question cannot overlap, but
        // a delayed/unavailable speech-synthesis callback can no longer hide
        // the first question and make the interview appear stuck.
        presentQuestion(msg);
        break;

      case 'transition':
        setIsThinking(false);
        queueAiMessage(msg.text, {
          status: 'Jack is updating the interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'coding_problem': {
        if (msg.problem) {
          setCodingProblem(msg.problem);
          setShowCodeEditor(true);
          // Pre-fill starter code for the current language if the editor is empty
          const lang = languageRef.current;
          setCode(prev => {
            if (prev && prev.trim()) return prev;
            const starter = msg.problem.starter_code || DEFAULT_STARTER_CODES;
            return starter[lang] || '';
          });
        }
        break;
      }

      case 'coding_submission_result':
        setIsSubmitting(false);
        setIsThinking(false);
        setSubmissionResult(msg);
        break;

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
          addCandidateMessage(msg.text);
          setStatusMessage('Jack is thinking about your answer…');
        } else if (msg.stage === 'evaluation') {
          setStatusMessage('Jack is evaluating your response…');
        }
        break;

      case 'tts_fallback':
        speakText(msg.text);
        break;

      case 'ai_response_text':
        queueAiMessage(msg.text, {
          status: 'Jack is speaking…',
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
  }, [queueAiMessage, speakText, openingIntro, addCandidateMessage]);

  // ── Serialized Audio Playback Queue ─────────────────────────────────
  // The backend streams TTS as multiple MP3 chunks. Every binary message is
  // queued here and played one at a time so chunks never overlap.
  const playNextAudioChunk = useCallback(() => {
    const queue = audioQueueRef.current;
    if (!queue.length) {
      isPlayingAudioRef.current = false;
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
      if (pendingQuestionTextRef.current) {
        setSubtitleText(pendingQuestionTextRef.current);
        pendingQuestionTextRef.current = null;
      }
      flushPendingQuestion();
      return;
    }
    if (pendingQuestionTextRef.current) {
      setSubtitleText(pendingQuestionTextRef.current);
      pendingQuestionTextRef.current = null;
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
  }, [finishAiResponse, clearLipSync, startAudioLevelMonitor, stopAudioLevelMonitor, flushPendingQuestion]);

  const handleAudioResponse = useCallback((arrayBuffer) => {
    // Text messages are spoken in one ordered browser queue when available.
    // Ignore delayed server audio so it cannot cancel or overlap that queue.
    if (supportsBrowserTts()) return;
    clearAudioFallbackTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    isSpeakingSpeechRef.current = false;
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

    const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${encodeURIComponent(token)}&interview_session_id=${encodeURIComponent(interviewSessionId)}&session_id=${encodeURIComponent(sessionId)}&client_tts=${supportsBrowserTts()}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('[AIInterviewer] WebSocket reconnected');
      setReconnectAttempts(0);
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          handleWsMessageRef.current(JSON.parse(event.data));
        } catch {
          setError('Received an invalid response from the interview service.');
          setPhase('error');
        }
      } else {
        handleAudioResponseRef.current(event.data);
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
  }, [interviewSessionId, token, sessionId, reconnectAttempts]);

  // Refs that always hold the latest message handlers so the WS callbacks
  // created in startInterview / reconnectWs never capture stale closures.
  const handleWsMessageRef = useRef(handleWsMessage);
  const handleAudioResponseRef = useRef(handleAudioResponse);
  const reconnectWsRef = useRef(reconnectWs);
  useEffect(() => {
    handleWsMessageRef.current = handleWsMessage;
    handleAudioResponseRef.current = handleAudioResponse;
    reconnectWsRef.current = reconnectWs;
  }, [handleWsMessage, handleAudioResponse, reconnectWs]);

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
    const type = file.type;
    const isValidExt = ['pdf', 'txt', 'docx'].includes(ext);
    const isValidType = ['application/pdf', 'text/plain', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'].includes(type);
    
    if (!isValidExt && !isValidType) {
      setResumeUploadError('Only PDF, DOCX, or TXT files are supported.');
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
    if (startInProgressRef.current || wsRef.current) return;
    startInProgressRef.current = true;
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
        const errorBody = await res.json().catch(() => ({}));
        throw new Error(errorBody.detail || errorBody.message || `Failed to initialize interview (${res.status})`);
      }

      const data = await res.json();
      const ivSessionId = data.interview_session_id;
      setInterviewSessionId(ivSessionId);
      if (data.status === 'resumable' && !resumableSession) {
        setResumableSession(ivSessionId);
      }

      const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${encodeURIComponent(token)}&interview_session_id=${encodeURIComponent(ivSessionId)}&session_id=${encodeURIComponent(activeSessionId)}&client_tts=${supportsBrowserTts()}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        console.log('[AIInterviewer] WebSocket connected');
        setPhase('opening');
        setStatusMessage('Connecting to Jack...');
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            handleWsMessageRef.current(JSON.parse(event.data));
          } catch {
            setError('Received an invalid response from the interview service.');
            setPhase('error');
          }
        } else {
          handleAudioResponseRef.current(event.data);
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
              reconnectWsRef.current();
            }
          }, 2000);
        }
      };

    } catch (err) {
      console.error('[AIInterviewer] Start failed', err);
      setError(err.message);
      setPhase('error');
    } finally {
      startInProgressRef.current = false;
    }
  }, [sessionId, token, effectiveRole, company, resumeText, resumableSession, uploadedSessionId]);

  // ── Direct IDE Mode Handler ─────────────────────────────────────────
  const startCodingDemo = useCallback(() => {
    const demoProblem = {
      id: 'demo-two-sum',
      title: 'Two Sum',
      topic: 'Arrays & Hashing',
      difficulty: 'easy',
      description:
        'Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input would have exactly one solution, and you may not use the same element twice.\n\nYou can return the answer in any order.',
      examples: [
        {
          input: 'nums = [2, 7, 11, 15], target = 9',
          output: '[0, 1]',
          explanation: 'Because nums[0] + nums[1] == 9, we return [0, 1].',
        },
        {
          input: 'nums = [3, 2, 4], target = 6',
          output: '[1, 2]',
          explanation: 'Because nums[1] + nums[2] == 6, we return [1, 2].',
        },
      ],
      constraints: [
        '2 <= nums.length <= 10^4',
        '-10^9 <= nums[i] <= 10^9',
        '-10^9 <= target <= 10^9',
        'Only one valid answer exists.',
      ],
      starter_code: {
        python: 'def two_sum(nums, target):\n    # Write your solution here\n    hashmap = {}\n    for i, num in enumerate(nums):\n        diff = target - num\n        if diff in hashmap:\n            return [hashmap[diff], i]\n        hashmap[num] = i\n    return []\n\n# Quick test run\nprint(two_sum([2, 7, 11, 15], 9))\n',
        javascript: 'function twoSum(nums, target) {\n    const map = new Map();\n    for (let i = 0; i < nums.length; i++) {\n        const diff = target - nums[i];\n        if (map.has(diff)) {\n            return [map.get(diff), i];\n        }\n        map.set(nums[i], i);\n    }\n    return [];\n}\n\nconsole.log(twoSum([2, 7, 11, 15], 9));\n',
        java: 'import java.util.HashMap;\nimport java.util.Arrays;\n\nclass Solution {\n    public static int[] twoSum(int[] nums, int target) {\n        HashMap<Integer, Integer> map = new HashMap<>();\n        for (int i = 0; i < nums.length; i++) {\n            int diff = target - nums[i];\n            if (map.containsKey(diff)) {\n                return new int[] { map.get(diff), i };\n            }\n            map.put(nums[i], i);\n        }\n        return new int[]{};\n    }\n    public static void main(String[] args) {\n        System.out.println(Arrays.toString(twoSum(new int[]{2, 7, 11, 15}, 9)));\n    }\n}\n',
        cpp: '#include <iostream>\n#include <vector>\n#include <unordered_map>\nusing namespace std;\n\nvector<int> twoSum(vector<int>& nums, int target) {\n    unordered_map<int, int> mp;\n    for (int i = 0; i < nums.size(); i++) {\n        int diff = target - nums[i];\n        if (mp.count(diff)) return {mp[diff], i};\n        mp[nums[i]] = i;\n    }\n    return {};\n}\n\nint main() {\n    vector<int> nums = {2, 7, 11, 15};\n    vector<int> ans = twoSum(nums, 9);\n    cout << "[" << ans[0] << ", " << ans[1] << "]" << endl;\n    return 0;\n}\n',
      },
      visible_test_cases: [
        { input: '[2, 7, 11, 15]\n9', expected_output: '[0, 1]' },
        { input: '[3, 2, 4]\n6', expected_output: '[1, 2]' },
      ],
    };

    const bankProblem = codingQuestions.length > 0
      ? codingQuestions[directQuestionIndex % codingQuestions.length]
      : null;
    const selectedProblem = normalizeDirectProblem(bankProblem || demoProblem);

    setIsDirectCodeMode(true);
    setCodingProblem(selectedProblem);
    const initialLang = language || 'python';
    setCode(selectedProblem.starter_code[initialLang] || selectedProblem.starter_code.python || '');
    setShowCodeEditor(true);
    setCurrentStage('Live Coding Challenge');
    setPhase('interviewing');
    setMessages([
      {
        id: Date.now(),
        role: 'interviewer',
        text: '⚡ Direct Code Editor Mode active! You can write, execute, and run unit tests on your code directly using the IDE on the right.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  }, [codingQuestions, directQuestionIndex, language]);

  const nextDirectProblem = useCallback(() => {
    if (!codingQuestions.length) return;
    const nextIndex = (directQuestionIndex + 1) % codingQuestions.length;
    const nextProblem = normalizeDirectProblem(codingQuestions[nextIndex]);
    setDirectQuestionIndex(nextIndex);
    setCodingProblem(nextProblem);
    setCode(nextProblem.starter_code?.[language] || nextProblem.starter_code?.python || '');
    setRunOutput('');
    setRunStatus('');
    setTestResults(null);
  }, [codingQuestions, directQuestionIndex, language]);

  const handleLanguageChange = useCallback((newLang) => {
    setLanguage(newLang);
    const starter = codingProblem?.starter_code?.[newLang] || DEFAULT_STARTER_CODES[newLang] || '';
    setCode(starter);
    setRunOutput('');
    setRunStatus('');
    setTestResults(null);
    setSubmissionResult(null);
  }, [codingProblem]);

  // ── Explicit start (Begin button) ────────────────────────────────────
  // The interview only starts on user action — no surprise mic/camera
  // requests on page load.
  const beginInterview = useCallback(async (resumeExisting = true) => {
    setIsDirectCodeMode(false);
    const allowed = await requestMicPermission();
    if (!allowed) setStatusMessage('Microphone unavailable. You can answer by typing.');
    await requestCameraPermission(); // optional — never blocks the interview
    startInterview(resumeExisting);
  }, [requestMicPermission, requestCameraPermission, startInterview]);

  // ── Send Text Answer ─────────────────────────────────────────────────
  const sendAnswer = useCallback((text) => {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();

    if (isDirectCodeMode) {
      return;
    }

    // Immediately add candidate message to the transcript
    addCandidateMessage(cleanText);

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    isSpeakingSpeechRef.current = false;
    speechQueueRef.current = [];
    setIsSpeaking(false);
    clearLipSync();

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setIsThinking(true);
      setTimeout(() => {
        setIsThinking(false);
        setMessages(prev => [
          ...prev,
          {
            id: Date.now(),
            role: 'interviewer',
            text: `[Offline Mode] Response received.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          }
        ]);
      }, 700);
      return;
    }

    addCandidateMessage(text);
    setIsThinking(true);
    setStatusMessage('Jack is thinking about your answer…');

    wsRef.current.send(JSON.stringify({
      type: 'answer',
      text: cleanText,
      code: code || undefined,
      language: code ? language : undefined,
    }));
  }, [code, language, addCandidateMessage, isDirectCodeMode, clearLipSync]);

  // ── Run Code ───────────────────────────────────────────────────────
  const runCode = useCallback(async () => {
    if (!code.trim() || isRunning || isTesting) return;
    const cases = codingProblem?.visible_test_cases || [];

    setIsRunning(true);
    setIsTesting(true);
    setRunOutput('');
    setTestResults(null);

    if (cases.length > 0) {
      setRunStatus('Running public test cases…');
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
          setRunStatus(data.detail || data.message || `Run failed (${res.status})`);
          setRunOutput(data.error || '');
          return;
        }
        setTestResults(data);
        const timedOut = (data.results || []).some((result) => result.status === 'timeout');
        setRunStatus(timedOut ? 'Time limit exceeded.' : `${data.passed || 0}/${data.total || cases.length} public cases checked.`);
      } catch (err) {
        setRunStatus('Could not contact run service.');
        setRunOutput(err.message || '');
      } finally {
        setIsRunning(false);
        setIsTesting(false);
      }
    } else {
      // General code runner without predefined test cases (runs code via backend /run-code)
      setRunStatus('Executing code…');
      try {
        const res = await fetch(`${API_BASE}/ai-interview/run-code`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ language, code, stdin: stdin || '' }),
        });
        const data = await res.json();
        if (!res.ok) {
          setRunStatus(data.detail || data.message || `Execution error (${res.status})`);
          setRunOutput(data.error || data.detail || '');
          return;
        }
        const output = data.stdout || data.stderr || data.error || '(Code executed with no output)';
        setRunOutput(output);
        setRunStatus(data.timed_out ? 'Execution timed out.' : (data.ok ? 'Execution successful.' : 'Execution finished with output.'));
      } catch (err) {
        setRunStatus('Could not contact run service.');
        setRunOutput(err.message || '');
      } finally {
        setIsRunning(false);
        setIsTesting(false);
      }
    }
  }, [code, language, token, codingProblem, isRunning, isTesting, stdin]);

  const submitCode = useCallback(() => {
    if (!code.trim() || isSubmitting || isDirectCodeMode) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setRunStatus('Interview connection is not available.');
      return;
    }
    setIsSubmitting(true);
    setSubmissionResult(null);
    setIsThinking(true);
    const summaryMsg = `Submitted ${language} solution for ${codingProblem?.title || 'the coding challenge'}.`;
    addCandidateMessage(summaryMsg);
    wsRef.current.send(JSON.stringify({
      type: 'answer',
      text: summaryMsg,
      code,
      language,
    }));
  }, [code, language, codingProblem, isSubmitting, isDirectCodeMode, addCandidateMessage]);

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
      candidateTurnStartRef.current = messagesRef.current.length;
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
          // Send audio end ONLY if we didn't already send it instantly in onstop
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
        
        // Immediately send to backend, don't wait for SpeechRecognition's onend latency
        if (!audioEndSentRef.current) {
          sendAudioEnd();
        }

        const sr = speechRecognitionRef.current;
        if (sr) {
          try { sr.stop(); } catch (err) { /* already stopped */ }
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
    if (isDirectCodeMode) {
      setPhase('idle');
      setIsDirectCodeMode(false);
      setShowCodeEditor(false);
      return;
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_voice' }));
      setIsThinking(true);
      setPhase('completing');
    }
  }, [isDirectCodeMode]);

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
          onRoleChange={setSelectedRole}
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
          onStartCodingDemo={startCodingDemo}
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
            <div className="aii-header__name">Jack</div>
            <div className="aii-header__subrow">
              <span className="aii-header__title">Technical Interviewer</span>
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

          {/* Code Editor toggle button */}
          {codingEnabled && <button
            className="aii-repeat-btn"
            onClick={() => {
              setShowCodeEditor((prev) => {
                const next = !prev;
                if (next && !codeRef.current.trim()) {
                  const lang = languageRef.current || 'python';
                  const starter = codingProblem?.starter_code?.[lang] || DEFAULT_STARTER_CODES[lang] || '';
                  setCode(starter);
                }
                return next;
              });
            }}
            title="Toggle Live Code Editor"
            style={{ background: 'rgba(99, 102, 241, 0.25)', borderColor: 'rgba(129, 140, 248, 0.5)' }}
          >
            <Code2 size="14" /> {showCodeEditor ? 'Close Code Editor' : 'Code Editor'}
          </button>}

          {/* Candidate webcam feed card — top right header placement */}
          <CandidateWebcamCard videoRef={videoRef} userStream={userStream} proctoringActive={isProctoringEnabled} />

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

      {/* Interview Room Main Body */}
      <div className={`aii-room__body ${showCodeEditor ? 'aii-room__body--split' : ''}`}>
        {/* Left Side: Avatar, Subtitles, Chat, Controls */}
        <div className="aii-room__left">
          <div className="aii-room__stage">
            <ObiAvatar state={avatarState} lipLevel={lipLevel} audioLevel={audioLevel} statusText={stageStatusText} />
            <div className="aii-subtitle-card">
              <div className="aii-subtitle-card__header">
                <div className="aii-subtitle-card__label"><Volume2 size="12" /> Current prompt</div>
                {subtitleText && phase === 'interviewing' && (
                  <button
                    className="aii-repeat-btn"
                    onClick={() => speakText(subtitleText)}
                    disabled={isSpeaking || isThinking}
                    title="Repeat Jack's question"
                  >
                    <RotateCcw size="12" /> Repeat
                  </button>
                )}
              </div>
              <p className="aii-subtitle-card__text">{subtitleText || 'Jack will speak here once the interview begins.'}</p>
            </div>
          </div>

          <div className="aii-room__panel">
            {phase === 'initializing' && (
              <div className="aii-init-message">
                <ObiAvatar compact state="connecting" />
                <div className="aii-spinner aii-spinner--sm" />
                <p>{statusMessage || 'Jack is reading your resume and preparing your interview…'}</p>
              </div>
            )}

            <div className="aii-chat__heading">Your Live Transcript</div>
            <div className="aii-chat">
              {messages.map((msg) => (
                <MessageBubble key={msg.id || `${msg.role}-${msg.ts}`} message={msg} />
              ))}
              {isProcessing && <div className="aii-transcript-status">Transcribing your speech...</div>}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area inside Left Side */}
          {phase === 'interviewing' && (
            <div className="aii-input-area aii-room__controls">
              <div className="aii-voice-controls">
                <div className="aii-voice-row">
                  <div className="aii-mic-wrap">
                    <button
                      className={`aii-mic-btn ${isRecording ? 'aii-mic-btn--recording' : ''}`}
                      onClick={() => {
                        if (isRecording) {
                          stopRecording();
                        } else {
                          startRecording();
                        }
                      }}
                      disabled={isThinking || isSpeaking}
                      title={isRecording ? 'Click to stop & send answer' : 'Click to start speaking'}
                      aria-label={isRecording ? 'Click to stop & send answer' : 'Click to start speaking'}
                    >
                      <Mic size="24" />
                    </button>
                    <span className="aii-mic-label">{isRecording ? 'Click to send' : 'Click to talk'}</span>
                  </div>

                  <div className="aii-voice-meta">
                    <WaveformVisualizer isActive={isRecording || isSpeaking} color={isRecording ? '#f87171' : '#818cf8'} />
                    <div className={`aii-voice-status aii-voice-status--${isRecording ? 'rec' : isSpeaking ? 'speak' : isThinking ? 'think' : 'idle'}`}>
                      {isRecording
                        ? <><span className="aii-voice-status__dot" /> Recording…</>
                        : isSpeaking
                          ? <><Volume2 size="14" /> Jack speaking…</>
                          : isThinking
                            ? <><Loader2 size="14" className="aii-spin" /> Thinking…</>
                            : <><Mic size="14" /> Ready to record</>}
                    </div>
                  </div>
                </div>

                <div className="aii-text-row">
                  <input
                    ref={textInputRef}
                    type="text"
                    className="aii-text-input"
                    placeholder="Or type your response to Jack…"
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
                    <Send size="16" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Side: Full IDE Workspace */}
        {showCodeEditor && (
          <div className="aii-room__right aii-code-workspace">
            <CodingPanel
              problem={codingProblem}
              language={language}
              onLanguageChange={handleLanguageChange}
              code={code}
              onCodeChange={setCode}
              stdin={stdin}
              onStdinChange={setStdin}
              runStatus={runStatus}
              runOutput={runOutput}
              isRunning={isRunning}
              isTesting={isTesting}
              isSubmitting={isSubmitting}
              isThinking={isThinking}
              testResults={testResults}
              submissionResult={submissionResult}
              onRun={runCode}
              onTest={runTests}
              onSubmit={submitCode}
              onReset={() => {
                const starter = codingProblem?.starter_code?.[language] || codingProblem?.starterCode?.[language] || '';
                setCode(starter);
                setRunOutput('');
                setRunStatus('');
                setTestResults(null);
                setSubmissionResult(null);
              }}
              onNextProblem={isDirectCodeMode ? nextDirectProblem : undefined}
              isDirectMode={isDirectCodeMode}
              languageOptions={LANGUAGE_OPTIONS}
            />
          </div>
        )}
      </div>

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
