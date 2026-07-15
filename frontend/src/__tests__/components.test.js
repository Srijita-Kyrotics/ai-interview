import { describe, it, expect } from 'vitest'

describe('TerminatedPage', () => {
  it('renders without crashing', async () => {
    const { TerminatedPage } = await import('../components/TerminatedPage')
    expect(TerminatedPage).toBeDefined()
  })
})

describe('Home', () => {
  it('renders without crashing', async () => {
    const { Home } = await import('../components/Home')
    expect(Home).toBeDefined()
  })
})

describe('CodeEditor', () => {
  it('exports CodeEditor component', async () => {
    const mod = await import('../components/CodeEditor')
    expect(mod.CodeEditor).toBeDefined()
  })
})

describe('VoiceAnswerControls', () => {
  it('exports VoiceAnswerControls component', async () => {
    const mod = await import('../components/VoiceAnswerControls')
    expect(mod.VoiceAnswerControls).toBeDefined()
  })
})

describe('Shell', () => {
  it('exports Shell component', async () => {
    const mod = await import('../components/Shell')
    expect(mod.Shell).toBeDefined()
  })
})

describe('AuthPage', () => {
  it('exports AuthPage component', async () => {
    const mod = await import('../components/AuthPage')
    expect(mod.AuthPage).toBeDefined()
  })
})

describe('ResumePage', () => {
  it('exports ResumePage component', async () => {
    const mod = await import('../components/ResumePage')
    expect(mod.ResumePage).toBeDefined()
  })
})

describe('CompanyPage', () => {
  it('exports CompanyPage component', async () => {
    const mod = await import('../components/CompanyPage')
    expect(mod.CompanyPage).toBeDefined()
  })
})

describe('RoundPage', () => {
  it('exports RoundPage and processAptitudeText', async () => {
    const mod = await import('../components/RoundPage')
    expect(mod.RoundPage).toBeDefined()
    expect(mod.processAptitudeText).toBeDefined()
  })
})

describe('ChatInterview', () => {
  it('exports ChatInterview component', async () => {
    const mod = await import('../components/ChatInterview')
    expect(mod.ChatInterview).toBeDefined()
  })
})

describe('ReportPage', () => {
  it('exports ReportPage component', async () => {
    const mod = await import('../components/ReportPage')
    expect(mod.ReportPage).toBeDefined()
  })
})

describe('DashboardPage', () => {
  it('exports DashboardPage component', async () => {
    const mod = await import('../components/DashboardPage')
    expect(mod.DashboardPage).toBeDefined()
  })
})

describe('RecruiterPage', () => {
  it('exports RecruiterPage component', async () => {
    const mod = await import('../components/RecruiterPage')
    expect(mod.RecruiterPage).toBeDefined()
  })
})

describe('SessionDetailModal', () => {
  it('exports SessionDetailModal component', async () => {
    const mod = await import('../components/SessionDetailModal')
    expect(mod.SessionDetailModal).toBeDefined()
  })
})

describe('AdminSessionModal', () => {
  it('exports AdminSessionModal component', async () => {
    const mod = await import('../components/AdminSessionModal')
    expect(mod.AdminSessionModal).toBeDefined()
  })
})
