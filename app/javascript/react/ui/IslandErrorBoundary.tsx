import * as Sentry from "@sentry/browser"
import { Component, type ErrorInfo, type ReactNode } from "react"

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

// Prevents a thrown error in an island component from unmounting the entire
// React root, which would leave a blank hole in the server-rendered page.
export class IslandErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("[React Island]", error)

    Sentry.withScope(scope => {
      scope.setContext("react", { componentStack: errorInfo.componentStack })
      scope.captureException(error)
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center p-6 text-sm text-base-content/60">
          <span>Something went wrong.</span>
          <button
            className="ml-2 underline hover:text-base-content"
            onClick={() => this.setState({ hasError: false })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
