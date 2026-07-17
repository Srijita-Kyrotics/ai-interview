import React, { useEffect, useState } from 'react'
import { Lock, Target, Zap, Eye, EyeOff } from 'lucide-react'
import { api } from '../api'

function AuthPage({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '', otp: '', captcha: '' })
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [otpStatus, setOtpStatus] = useState('')
  const [captcha, setCaptcha] = useState({ token: '', question: '' })
  const [isSendingOtp, setIsSendingOtp] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [otpRequested, setOtpRequested] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const isCreate = mode === 'create'

  const loadCaptcha = async () => {
    const res = await api.get('/auth/captcha')
    setCaptcha({ token: res.token, question: res.question })
    setForm((current) => ({ ...current, captcha: '' }))
  }

  useEffect(() => {
    loadCaptcha()
  }, [])

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
    if (!/[^A-Za-z0-9]/.test(trimmed)) return 'Password must include at least one special character.'
    return ''
  }

  const validateName = (value) => {
    if (isCreate && !value.trim()) return 'Your full name is required.'
    return ''
  }

  const validateConfirmPassword = (value) => {
    const trimmedValue = value?.trim() || ''
    const trimmedPassword = form.password?.trim() || ''
    if (!trimmedValue) return 'Please confirm your password.'
    if (trimmedValue !== trimmedPassword) return 'Passwords do not match.'
    return ''
  }

  const validateOtp = (value) => {
    if (!value) return 'Enter the one-time code sent to your email.'
    return ''
  }

  const validateCaptcha = (value) => {
    if (!value) return 'Enter the captcha answer.'
    return ''
  }

  const isEmailValid = Boolean(form.email && !validateEmail(form.email))
  const showCredentials = isEmailValid
  const passwordValidationMessage = form.password ? validatePassword(form.password) : 'Create a strong password to continue.'
  const confirmValidationMessage = isCreate ? (form.confirmPassword ? validateConfirmPassword(form.confirmPassword) : 'Confirm your password.') : ''
  const canRequestOtp = showCredentials && !passwordValidationMessage && (!isCreate || !confirmValidationMessage) && (!isCreate || !!form.name.trim())

  const sendOtp = async () => {
    const email = form.email.trim().toLowerCase()
    const password = form.password
    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmError = isCreate ? validateConfirmPassword(form.confirmPassword) : ''
    const nameError = isCreate ? validateName(form.name) : ''

    const newErrors = {
      email: emailError,
      password: passwordError,
      confirmPassword: confirmError,
      name: nameError
    }
    setFieldErrors(newErrors)

    if (emailError) {
      setError('Enter a valid email address before requesting OTP.')
      return
    }

    if (nameError) {
      setError(nameError)
      return
    }

    if (passwordError || confirmError) {
      setError(passwordError || confirmError || 'Fix your password before requesting OTP.')
      return
    }

    setIsSendingOtp(true)
    setError('')
    setOtpStatus('')
    try {
      if (!isCreate) {
        const emailCheck = await api.post('/auth/check-email', { email })
        if (!emailCheck.ok || !emailCheck.exists) {
          setError('Email not found. Please register with this email first.')
          return
        }
      }
      if (isCreate) {
        const emailCheck = await api.post('/auth/check-email', { email })
        if (emailCheck.ok && emailCheck.exists) {
          setError('An account already exists for this email. Please login instead.')
          return
        }
      }
      const res = await api.post('/auth/send-otp', { email })
      if (!res.ok) {
        setError(res.error || 'Could not send OTP.')
        return
      }
      setOtpRequested(true)
      setOtpStatus(res.dev_otp ? `${res.message} Development OTP: ${res.dev_otp}` : res.message)
    } catch {
      setError('Could not contact the OTP service.')
    } finally {
      setIsSendingOtp(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const password = form.password
    const confirmPassword = form.confirmPassword
    const otp = form.otp.trim()
    const captchaAnswer = form.captcha.trim()

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmError = isCreate ? validateConfirmPassword(confirmPassword) : ''
    const nameError = isCreate ? validateName(form.name) : ''
    const otpError = validateOtp(otp)
    const captchaError = validateCaptcha(captchaAnswer)

    const newErrors = {
      email: emailError,
      password: passwordError,
      confirmPassword: confirmError,
      name: nameError,
      otp: otpRequested ? otpError : '',
      captcha: otpRequested ? captchaError : ''
    }
    setFieldErrors(newErrors)

    if (emailError || passwordError || confirmError || nameError || otpError || captchaError) {
      setError('Please correct the highlighted fields before continuing.')
      return
    }

    if (!otpRequested) {
      setError('Request your OTP first, then confirm it with the captcha.')
      return
    }

    setIsSubmitting(true)
    setError('')
    try {
      const endpoint = isCreate ? '/auth/register' : '/auth/login'
      const payload = {
        email,
        password,
        otp,
        captcha_token: captcha.token,
        captcha_answer: captchaAnswer
      }
      if (isCreate) payload.name = form.name.trim()

      const res = await api.post(endpoint, payload)
      if (!res.ok) {
        setError(res.error || 'Verification failed.')
        await loadCaptcha()
        return
      }
      if (isCreate) {
        const user = { name: res.user?.name || form.name.trim(), email, role: res.user?.role || 'candidate', token: res.token }
        localStorage.setItem('mockRecruitmentUser', JSON.stringify(user))
        onAuth(user)
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
          <p>Sign in with your email, request an OTP, and verify with captcha to access the interview simulator.</p>
        </div>
        <div className="feature-list" aria-hidden="true">
          <div className="feature-card">
            <span><Lock size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Secure access</span>
            <p>Email + OTP + captcha verification keeps your session protected end-to-end.</p>
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
            <h2>{isCreate ? 'Create your account' : 'Welcome back'}</h2>
            <p className="muted">Sign in first, then upload a resume and choose the company interview to practice.</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={submit}>
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
              />
              {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
            </label>
            {showCredentials ? (
              <>
                {isCreate && (
                  <label>
                    Full name
                    <input
                      className={`input ${fieldErrors.name ? 'invalid' : ''}`}
                      value={form.name}
                      onChange={(e) => updateField('name', e.target.value)}
                      placeholder="Jane Doe"
                    />
                    {fieldErrors.name ? <div className="field-error">{fieldErrors.name}</div> : null}
                  </label>
                )}
                <label>
                  {isCreate ? 'Create password' : 'Password'}
                  <div className="password-field-wrapper">
                    <input
                      className={`input ${fieldErrors.password ? 'invalid' : ''}`}
                      type={showPassword ? 'text' : 'password'}
                      value={form.password}
                      onChange={(e) => updateField('password', e.target.value)}
                      placeholder="At least 8 characters and a special character"
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
                {isCreate && (
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
                )}
                {!canRequestOtp && !otpRequested ? (
                  <div className="notice info">
                    {isCreate
                      ? passwordValidationMessage || confirmValidationMessage || 'Fill the password fields correctly to send OTP.'
                      : passwordValidationMessage || 'Enter your password correctly to send OTP.'}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="notice info">Enter a valid email to continue with account creation or login.</div>
            )}
          </div>

          {(canRequestOtp || otpRequested) && (
            <div className="form-section">
              <div className="section-title">Secure access</div>
              <label>
                One-time code
                <button className="btn ghost" type="button" disabled={isSendingOtp || !canRequestOtp} onClick={sendOtp}>
                  {isSendingOtp ? 'Sending\u2026' : otpRequested ? 'Resend OTP' : 'Send OTP'}
                </button>
                <input
                  className={`input ${fieldErrors.otp ? 'invalid' : ''}`}
                  inputMode="numeric"
                  value={form.otp}
                  onChange={(e) => updateField('otp', e.target.value)}
                  placeholder="Enter OTP"
                  disabled={!otpRequested}
                />
                {fieldErrors.otp ? <div className="field-error">{fieldErrors.otp}</div> : null}
              </label>
              {otpStatus ? <div className="secure-note">{otpStatus}</div> : null}
              <label>
                Captcha verification
                <div className="captcha-box">
                  <div className="captcha-question">{captcha.question || 'Loading captcha...'}</div>
                  <button className="btn ghost" type="button" onClick={loadCaptcha}>Refresh</button>
                </div>
                <input
                  className={`input ${fieldErrors.captcha ? 'invalid' : ''}`}
                  inputMode="numeric"
                  value={form.captcha}
                  onChange={(e) => updateField('captcha', e.target.value)}
                  placeholder="Answer the captcha"
                  disabled={!otpRequested}
                />
                {fieldErrors.captcha ? <div className="field-error">{fieldErrors.captcha}</div> : null}
              </label>
            </div>
          )}

          {error ? <div className="notice danger">{error}</div> : null}
          <button className="btn primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Verifying\u2026' : isCreate ? 'Create account' : 'Login'}
          </button>
        </form>

        <button
          className="link-button"
          type="button"
          onClick={() => {
            setError('')
            setFieldErrors({})
            setOtpStatus('')
            setOtpRequested(false)
            setForm({ name: '', email: '', password: '', confirmPassword: '', otp: '', captcha: '' })
            loadCaptcha()
            setMode(isCreate ? 'login' : 'create')
          }}
        >
          {isCreate ? 'Already have an account? Login' : 'New user? Create account'}
        </button>
      </section>
    </div>
  )
}

export { AuthPage }
