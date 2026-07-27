import React from 'react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
          alignItems: 'center', height: '100vh', padding: '24px',
          backgroundColor: '#0f172a', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif'
        }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '12px' }}>Something went wrong</h1>
          <p style={{ color: '#94a3b8', marginBottom: '24px', textAlign: 'center', maxWidth: '480px' }}>
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              className="btn primary"
              onClick={this.handleReset}
            >
              Try again
            </button>
            <button
              className="btn"
              onClick={() => { window.location.href = '/' }}
            >
              Go home
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
