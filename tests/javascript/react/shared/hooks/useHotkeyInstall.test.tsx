import { render } from "@testing-library/react"
import { useRef } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"

const install = vi.hoisted(() => vi.fn())
const uninstall = vi.hoisted(() => vi.fn())
vi.mock("@github/hotkey", () => ({ install, uninstall }))

// Reset in beforeEach (not afterEach): testing-library's auto-cleanup unmounts the
// prior test's tree during afterEach and fires uninstall — resetting here clears
// those leaked calls before the next test's assertions.
beforeEach(() => {
  install.mockReset()
  uninstall.mockReset()
})

// A minimal harness that renders whatever markup the test supplies inside a ref'd
// container wired to useHotkeyInstall — mirrors how MailboxActionBar drives it.
function Harness({ enabled, children }: { enabled?: boolean; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useHotkeyInstall(ref, enabled)
  return <div ref={ref}>{children}</div>
}

// A MutationObserver callback is delivered in a microtask; flush it.
const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe("useHotkeyInstall", () => {
  it("installs data-hotkey nodes present at mount and uninstalls on unmount", () => {
    const { unmount } = render(
      <Harness>
        <button data-hotkey="e">Archive</button>
      </Harness>
    )
    expect(install).toHaveBeenCalledTimes(1)

    unmount()
    expect(uninstall).toHaveBeenCalledTimes(1)
  })

  it("installs nothing while disabled", () => {
    render(
      <Harness enabled={false}>
        <button data-hotkey="e">Archive</button>
      </Harness>
    )
    expect(install).not.toHaveBeenCalled()
  })

  it("installs a data-hotkey added after mount (async nav arrow gaining its hotkey)", async () => {
    function Toggling({ ready }: { ready: boolean }) {
      return <Harness>{ready ? <button data-hotkey="ArrowRight">Next</button> : <button>Next</button>}</Harness>
    }
    const { rerender } = render(<Toggling ready={false} />)
    expect(install).not.toHaveBeenCalled()

    rerender(<Toggling ready={true} />)
    await flush()
    expect(install).toHaveBeenCalledTimes(1)
  })

  it("uninstalls a data-hotkey removed after mount", async () => {
    function Toggling({ ready }: { ready: boolean }) {
      return <Harness>{ready ? <button data-hotkey="ArrowRight">Next</button> : <button>Next</button>}</Harness>
    }
    const { rerender } = render(<Toggling ready={true} />)
    expect(install).toHaveBeenCalledTimes(1)

    rerender(<Toggling ready={false} />)
    await flush()
    expect(uninstall).toHaveBeenCalledTimes(1)
  })
})
