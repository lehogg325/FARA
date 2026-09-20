import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Render errors have no functional-component equivalent — getDerivedStateFromError/
// componentDidCatch only exist on class components. Without this, any component
// throwing during render unmounts the whole tree (React's default with no boundary
// present), leaving every visitor with a blank page and no way to recover short of
// a hard reload.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Render error caught by ErrorBoundary:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-state" style={{ padding: "60px 0" }}>
          Something went wrong displaying this page.
          <div style={{ marginTop: 12 }}>
            <button className="back-link" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
