import React, { useState } from 'react'
import { Lock, Target, Zap, Eye, EyeOff } from 'lucide-react'
import { api } from '../api'

function AuthPage({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '', resetToken: '', newPassword: '', confirmNewPassword: '' })
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmNewPassword, setShowConfirmNewPassword] = useState(false)
  const [devToken, setDevToken] = useState('')
  const [resetEmailSent, setResetEmailSent] = useState(false)
  const [resetSuccess, setResetSuccess] = useState(false)
  const isCreate = mode === 'create'
  const isForgot = mode === 'forgot'
  const isReset = mode === 'reset'

  const updateField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }))
    setError('')
    setFieldErrors((current) => ({ ...current, [key]: '' }))
  }

  const validateEmail = (value) => {
    if (!value) return 'Email is required.'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Enter a valid email address.'
    return ''
  }

  const validatePassword = (value) => {
    const trimmed = value?.trim() || ''
    if (!trimmed) return 'Password is required.'
    if (trimmed.length < 8) return 'Password must be at least 8 characters long.'
    if (!/[A-Z]/.test(trimmed)) return 'Password must include at least one uppercase letter.'
    if (!/[0-9]/.test(trimmed)) return 'Password must include at least one digit.'
    return ''
  }

  const validateName = (value) => {
    if (isCreate && !value.trim()) return 'Your full name is required.'
    return ''
  }

  const validateConfirmPassword = (value, passwordField) => {
    const trimmedValue = value?.trim() || ''
    const trimmedPassword = (passwordField || form.password)?.trim() || ''
    if (!trimmedValue) return 'Please confirm your password.'
    if (trimmedValue !== trimmedPassword) return 'Passwords do not match.'
    return ''
  }

  const submitLogin = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const password = form.password

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)

    const newErrors = { email: emailError, password: passwordError }
    setFieldErrors(newErrors)

    if (emailError || passwordError) {
      setError('Please correct the highlighted fields before continuing.')
      return
    }

    setIsSubmitting(true)
    setError('')
    try {
      const res = await api.post('/auth/login', { email, password })
      if (!res.ok) {
        setError(res.error || 'Verification failed.')
        return
      }
      const user = { name: res.user?.name || res.name || email.split('@')[0], email, role: res.user?.role || 'candidate', token: res.token }
      localStorage.setItem('mockRecruitmentUser', JSON.stringify(user))
      onAuth(user)
    } catch {
      setError('Could not verify credentials.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const submitCreate = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const password = form.password
    const confirmPassword = form.confirmPassword

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmError = validateConfirmPassword(confirmPassword)
    const nameError = validateName(form.name)

    const newErrors = { email: emailError, password: passwordError, confirmPassword: confirmError, name: nameError }
    setFieldErrors(newErrors)

    if (emailError || passwordError || confirmError || nameError) {
      setError('Please correct the highlighted fields before continuing.')
      return
    }

    setIsSubmitting(true)
    setError('')
    try {
      const res = await api.post('/auth/register', { email, password, name: form.name.trim() })
      if (!res.ok) {
        setError(res.error || 'Registration failed.')
        return
      }
      const user = { name: res.user?.name || form.name.trim(), email, role: res.user?.role || 'candidate', token: res.token }
      localStorage.setItem('mockRecruitmentUser', JSON.stringify(user))
      onAuth(user)
    } catch {
      setError('Could not complete registration.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const submitForgot = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const emailError = validateEmail(email)

    setFieldErrors({ email: emailError })
    if (emailError) {
      setError(emailError)
      return
    }

    setIsSubmitting(true)
    setError('')
    setDevToken('')
    try {
      const res = await api.post('/auth/forgot-password', { email })
      if (!res.ok) {
        setError(res.error || 'Could not send reset token.')
        return
      }
      setResetEmailSent(true)
      if (res.dev_token) setDevToken(res.dev_token)
    } catch {
      setError('Could not contact the server.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const submitReset = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const token = form.resetToken.trim()
    const newPassword = form.newPassword
    const confirmNewPassword = form.confirmNewPassword

    const emailError = validateEmail(email)
    const passwordError = validatePassword(newPassword)
    const confirmError = validateConfirmPassword(confirmNewPassword, newPassword)

    const newErrors = { email: emailError, newPassword: passwordError, confirmNewPassword: confirmError }
    setFieldErrors(newErrors)

    if (emailError || passwordError || confirmError) {
      setError('Please correct the highlighted fields before continuing.')
      return
    }

    if (!token) {
      setFieldErrors((current) => ({ ...current, resetToken: 'Reset token is required.' }))
      setError('Enter the reset token you received.')
      return
    }

    setIsSubmitting(true)
    setError('')
    try {
      const res = await api.post('/auth/reset-password', { email, token, new_password: newPassword })
      if (!res.ok) {
        setError(res.error || 'Reset failed.')
        return
      }
      setResetSuccess(true)
    } catch {
      setError('Could not complete password reset.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const resetAllAndSwitch = (newMode) => {
    setError('')
    setFieldErrors({})
    setDevToken('')
    setResetEmailSent(false)
    setResetSuccess(false)
    setForm({ name: '', email: '', password: '', confirmPassword: '', resetToken: '', newPassword: '', confirmNewPassword: '' })
    setMode(newMode)
  }

  const panelTitle = isCreate ? 'Create your account' : isForgot ? 'Reset your password' : isReset ? 'Set new password' : 'Welcome back'
  const panelSubtitle = isCreate
    ? 'Sign up to start practicing mock interviews.'
    : isForgot
      ? 'Enter your email and we\'ll send you a reset token.'
      : isReset
        ? 'Enter the token from your email and your new password.'
        : 'Sign in to access the interview simulator.'

  return (
    <div className="auth-screen">
      {/* Ambient orbs */}
      <div className="orb orb-1" aria-hidden="true" />
      <div className="orb orb-2" aria-hidden="true" />

      <section className="auth-visual">
        <div className="auth-visual-grid" aria-hidden="true" />
        <div className="welcome-message">
          <div className="brand-badge">AI-Powered Mock  Recruitment Platform</div>
          <h1>AI Interview Coach</h1>
          <p>Sign in with your email and password to access the interview simulator.</p>
        </div>
        <div className="feature-list" aria-hidden="true">
          <div className="feature-card">
            <span><Lock size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Secure access</span>
            <p>Email and password verification keeps your session protected end-to-end.</p>
          </div>
          <div className="feature-card">
            <span><Target size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Practice workflow</span>
            <p>Upload a resume, choose a target company or the role based on your profile, and simulate real interview rounds.</p>
          </div>
          <div className="feature-card">
            <span><Zap size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Instant feedback</span>
            <p>Get AI-driven performance analytics and readiness scores after every round.</p>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Candidate access</p>
            <h2>{panelTitle}</h2>
            <p className="muted">{panelSubtitle}</p>
          </div>
        </div>

        {/* ── Login form ──────────────────────────────────────── */}
        {mode === 'login' && (
          <form className="auth-form" onSubmit={submitLogin}>
            <div className="form-section">
              <div className="section-title">Account details</div>
              <label>
                Email
                <input
                  className={`input ${fieldErrors.email ? 'invalid' : ''}`}
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField('email', e.target.value)}
                  placeholder="you@example.com"
                  aria-label="Email address"
                />
                {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
              </label>
              <label>
                Password
                <div className="password-field-wrapper">
                  <input
                    className={`input ${fieldErrors.password ? 'invalid' : ''}`}
                    type={showPassword ? 'text' : 'password'}
                    value={form.password}
                    onChange={(e) => updateField('password', e.target.value)}
                    placeholder="Enter your password"
                    aria-label="Password"
                  />
                  <button
                    className="eye-toggle"
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldErrors.password ? <div className="field-error">{fieldErrors.password}</div> : null}
              </label>
            </div>

            {error ? <div className="notice danger">{error}</div> : null}
            <button className="btn primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Verifying\u2026' : 'Login'}
            </button>
          </form>
        )}

        {/* ── Create account form ─────────────────────────────── */}
        {mode === 'create' && (
          <form className="auth-form" onSubmit={submitCreate}>
            <div className="form-section">
              <div className="section-title">Account details</div>
              <label>
                Email
                <input
                  className={`input ${fieldErrors.email ? 'invalid' : ''}`}
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField('email', e.target.value)}
                  placeholder="you@example.com"
                  aria-label="Email address"
                />
                {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
              </label>
              <label>
                Full name
                <input
                  className={`input ${fieldErrors.name ? 'invalid' : ''}`}
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder="Jane Doe"
                  aria-label="Full name"
                />
                {fieldErrors.name ? <div className="field-error">{fieldErrors.name}</div> : null}
              </label>
              <label>
                Create password
                <div className="password-field-wrapper">
                  <input
                    className={`input ${fieldErrors.password ? 'invalid' : ''}`}
                    type={showPassword ? 'text' : 'password'}
                    value={form.password}
                    onChange={(e) => updateField('password', e.target.value)}
                    placeholder="At least 8 characters, an uppercase letter, and a digit"
                    aria-label="Create password"
                  />
                  <button
                    className="eye-toggle"
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldErrors.password ? <div className="field-error">{fieldErrors.password}</div> : null}
              </label>
              <label>
                Confirm password
                <div className="password-field-wrapper">
                  <input
                    className={`input ${fieldErrors.confirmPassword ? 'invalid' : ''}`}
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={form.confirmPassword}
                    onChange={(e) => updateField('confirmPassword', e.target.value)}
                    placeholder="Repeat your password"
                  />
                  <button
                    className="eye-toggle"
                    type="button"
                    onClick={() => setShowConfirmPassword((current) => !current)}
                    aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                  >
                    {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldErrors.confirmPassword ? <div className="field-error">{fieldErrors.confirmPassword}</div> : null}
              </label>
            </div>

            {error ? <div className="notice danger">{error}</div> : null}
            <button className="btn primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Verifying\u2026' : 'Create account'}
            </button>
          </form>
        )}

        {/* ── Forgot password form (step 1: request token) ──── */}
        {mode === 'forgot' && !resetEmailSent && (
          <form className="auth-form" onSubmit={submitForgot}>
            <div className="form-section">
              <div className="section-title">Account lookup</div>
              <label>
                Email
                <input
                  className={`input ${fieldErrors.email ? 'invalid' : ''}`}
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField('email', e.target.value)}
                  placeholder="you@example.com"
                  aria-label="Email address"
                />
                {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
              </label>
            </div>

            {error ? <div className="notice danger">{error}</div> : null}
            <button className="btn primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Sending\u2026' : 'Send reset token'}
            </button>
          </form>
        )}

        {/* ── Forgot password form (step 2: token sent) ──────── */}
        {mode === 'forgot' && resetEmailSent && !resetSuccess && (
          <form className="auth-form" onSubmit={(e) => { e.preventDefault(); resetAllAndSwitch('reset') }}>
            <div className="notice success">Reset token sent. Check your email.</div>
            {devToken && (
              <div className="notice info" style={{ wordBreak: 'break-all' }}>
                <strong>Development token:</strong> {devToken}
              </div>
            )}

            {error ? <div className="notice danger">{error}</div> : null}
            <button className="btn primary" type="submit">
              Enter reset token
            </button>
          </form>
        )}

        {/* ── Reset password form (step 3: enter token + new password) */}
        {mode === 'reset' && !resetSuccess && (
          <form className="auth-form" onSubmit={submitReset}>
            <div className="form-section">
              <div className="section-title">Reset password</div>
              <label>
                Email
                <input
                  className={`input ${fieldErrors.email ? 'invalid' : ''}`}
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField('email', e.target.value)}
                  placeholder="you@example.com"
                  aria-label="Email address"
                />
                {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
              </label>
              <label>
                Reset token
                <input
                  className={`input ${fieldErrors.resetToken ? 'invalid' : ''}`}
                  value={form.resetToken}
                  onChange={(e) => updateField('resetToken', e.target.value)}
                  placeholder="Paste the reset token"
                  aria-label="Reset token"
                />
                {fieldErrors.resetToken ? <div className="field-error">{fieldErrors.resetToken}</div> : null}
              </label>
              <label>
                New password
                <div className="password-field-wrapper">
                  <input
                    className={`input ${fieldErrors.newPassword ? 'invalid' : ''}`}
                    type={showNewPassword ? 'text' : 'password'}
                    value={form.newPassword}
                    onChange={(e) => updateField('newPassword', e.target.value)}
                    placeholder="At least 8 characters, an uppercase letter, and a digit"
                    aria-label="New password"
                  />
                  <button
                    className="eye-toggle"
                    type="button"
                    onClick={() => setShowNewPassword((current) => !current)}
                    aria-label={showNewPassword ? 'Hide password' : 'Show password'}
                  >
                    {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldErrors.newPassword ? <div className="field-error">{fieldErrors.newPassword}</div> : null}
              </label>
              <label>
                Confirm new password
                <div className="password-field-wrapper">
                  <input
                    className={`input ${fieldErrors.confirmNewPassword ? 'invalid' : ''}`}
                    type={showConfirmNewPassword ? 'text' : 'password'}
                    value={form.confirmNewPassword}
                    onChange={(e) => updateField('confirmNewPassword', e.target.value)}
                    placeholder="Repeat your new password"
                  />
                  <button
                    className="eye-toggle"
                    type="button"
                    onClick={() => setShowConfirmNewPassword((current) => !current)}
                    aria-label={showConfirmNewPassword ? 'Hide confirm password' : 'Show confirm password'}
                  >
                    {showConfirmNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldErrors.confirmNewPassword ? <div className="field-error">{fieldErrors.confirmNewPassword}</div> : null}
              </label>
            </div>

            {error ? <div className="notice danger">{error}</div> : null}
            <button className="btn primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Resetting\u2026' : 'Reset password'}
            </button>
          </form>
        )}

        {/* ── Reset success ──────────────────────────────────── */}
        {resetSuccess && (
          <div className="auth-form">
            <div className="notice success">Password reset successful! You can now login with your new password.</div>
            <button className="btn primary" type="button" onClick={() => resetAllAndSwitch('login')}>
              Go to login
            </button>
          </div>
        )}

        {/* ── Footer links ───────────────────────────────────── */}
        {mode === 'login' && (
          <button
            className="link-button"
            type="button"
            onClick={() => resetAllAndSwitch('forgot')}
          >
            Forgot password?
          </button>
        )}

        {(mode === 'login' || mode === 'create') && (
          <button
            className="link-button"
            type="button"
            onClick={() => resetAllAndSwitch(isCreate ? 'login' : 'create')}
          >
            {isCreate ? 'Already have an account? Login' : 'New user? Create account'}
          </button>
        )}

        {(mode === 'forgot' || mode === 'reset') && (
          <button
            className="link-button"
            type="button"
            onClick={() => resetAllAndSwitch('login')}
          >
            Back to login
          </button>
        )}
      </section>
    </div>
  )
}

export { AuthPage }
