# AI-Interview Platform: Simple User Flow

This document explains the platform in simple terms. It focuses on what happens for a candidate and for the people reviewing the interview.

## The complete journey

```text
Candidate opens platform
  -> signs in or starts as a guest
  -> uploads resume
  -> chooses the job/company/assessment path
  -> starts the interview
  -> answers questions by voice or typing
  -> completes coding task when asked
  -> receives an interview report
  -> recruiter can review the results
```

## Step-by-step flow

### 1. Candidate enters the platform

The candidate opens the platform and signs in. For demo or quick-access use, the platform can also create a guest session.

The candidate then sees the interview setup screen.

### 2. Candidate uploads a resume

The candidate uploads a PDF or text resume, or pastes the resume content into the platform.

The platform reads the resume and picks up useful information such as:

- name and contact information;
- skills and technologies;
- work experience;
- projects;
- education and certifications.

This helps the interview feel relevant to the candidate instead of asking the same generic questions to everyone.

### 3. Candidate selects an interview path

Depending on the platform journey, the candidate can choose a company and take regular assessment rounds such as:

- aptitude;
- coding;
- technical;
- HR/behavioral.

Or, the candidate can directly begin the AI interview. The platform can also suggest a suitable role from the candidate's resume.

### 4. The AI interviewer prepares the session

When the candidate starts, Jack, the AI interviewer, welcomes them.

While the welcome message is being shown, the platform reviews the resume and prepares an interview plan. It decides which areas to explore, for example:

- the candidate's projects;
- skills mentioned in the resume;
- technical fundamentals;
- problem solving;
- teamwork and communication;
- system design, when relevant.

The candidate does not need to wait through a technical setup screen. They see Jack's greeting and then receive the first question.

### 5. Candidate answers questions

Jack asks one question at a time.

The candidate can answer in either of these ways:

- speak using the microphone;
- type an answer in the response box.

The candidate's response appears in the conversation history so they can follow the discussion.

### 6. The interview adapts to the candidate

After each answer, the platform checks whether the answer was clear, complete, and relevant.

Then Jack does one of the following:

```text
If the answer needs more detail
  -> Jack asks a follow-up question.

If the answer is good and the topic is complete
  -> Jack moves to the next topic.

If the candidate is doing very well
  -> Jack can ask more challenging questions.

If the candidate needs support or has a weak area
  -> Jack can ask simpler or more focused questions.
```

Jack also checks claims from the resume. For example, if a resume says the candidate built a system using Redis or React, Jack may ask about that project to understand the candidate's actual contribution and knowledge.

### 7. Live coding, when needed

For coding-related interviews, Jack can open a coding workspace during the conversation.

The candidate sees:

- the coding problem statement;
- examples and constraints;
- a code editor;
- programming language options;
- buttons to run the code and check results.

The candidate writes code, runs it, and can test it against visible examples. When ready, they submit the solution.

The platform checks the code and includes the outcome in the interview evaluation. The candidate can still discuss their approach with Jack while coding.

### 8. Interview integrity checks

If proctoring is enabled, the platform can monitor interview integrity signals such as leaving the interview tab, exiting full-screen mode, or camera-based checks.

If issues occur, the candidate receives warnings. Serious or repeated violations can end the session. This keeps the assessment fair.

### 9. Interview completion

The interview ends when Jack has covered the planned topics, reached the question limit, or the candidate chooses to end the session.

The platform then prepares a final report. It does not simply count answers; it combines information from the whole interview, including:

- technical knowledge;
- problem-solving ability;
- communication and clarity;
- confidence and answer depth;
- behavioral responses;
- coding performance, if a coding task was used;
- strengths and areas to improve.

### 10. Candidate receives results

After the interview, the candidate is taken to the report page.

The report gives an easy-to-understand summary of performance, scores, strengths, weaknesses, and suggested areas for practice.

### 11. Recruiter reviews the interview

Recruiters and administrators can review completed interviews from the recruiter/dashboard area.

They can use the result to understand:

- how the candidate performed overall;
- which skills were strong;
- which areas need attention;
- the interview conversation and progress;
- coding outcomes;
- integrity/proctoring information, when enabled.

## What happens if something interrupts the interview?

The platform saves the ongoing AI interview as it progresses. If the connection drops or the candidate returns later, the platform can restore the interview and continue from the current question when the active session is still available.

## One-line summary

**A candidate shares their resume, Jack creates a personalized interview, asks adaptive questions, opens a coding task when appropriate, evaluates the complete performance, and produces a report for the candidate and recruiter.**
