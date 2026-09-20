import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  onRetry: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Prevent a single render error from leaving a blank webview. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Graf-Id UI error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-shell app-shell--centered">
          <div className="startup">
            <h1>Something went wrong</h1>
            <p className="error-text">{this.state.error.message}</p>
            <button type="button" onClick={() => this.setState({ error: null }, this.props.onRetry)}>
              Reload dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
