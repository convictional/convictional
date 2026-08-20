import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { PushNotificationsSection } from "../../../../../app/javascript/react/features/notifications/components/PushNotificationsSection"
import type { PushSubscriptionDevice } from "../../../../../app/javascript/react/features/notifications/pushSubscription"

const enableMock = vi.fn()
const disableMock = vi.fn()
const isSupportedMock = vi.fn(() => true)
const currentPermissionMock = vi.fn<() => NotificationPermission>(() => "default")
const currentDeviceSuffixMock = vi.fn<() => Promise<string | null>>(() => Promise.resolve(null))

vi.mock("../../../../../app/javascript/react/features/notifications/pushSubscription", () => ({
  enablePushOnThisDevice: (...args: unknown[]) => enableMock(...args),
  disableDevice: (...args: unknown[]) => disableMock(...args),
  isPushSupported: () => isSupportedMock(),
  getCurrentPermission: () => currentPermissionMock(),
  getCurrentDeviceEndpointSuffix: () => currentDeviceSuffixMock(),
  PushPermissionDeniedError: class extends Error {
    constructor() {
      super("Notification permission denied")
      this.name = "PushPermissionDeniedError"
    }
  },
  PushUnsupportedError: class extends Error {
    constructor() {
      super("Push notifications are not supported in this browser")
      this.name = "PushUnsupportedError"
    }
  },
}))

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  errorMessage: (err: unknown, fallback: string) => (err instanceof Error && err.message ? err.message : fallback),
  ApiError: class extends Error {},
}))

function makeDevice(overrides: Partial<PushSubscriptionDevice> = {}): PushSubscriptionDevice {
  return {
    id: "device-1",
    endpoint_suffix: "…end/abc123",
    user_agent: "Mozilla/5.0",
    platform: "Chrome on macOS",
    created_at: "2026-05-12T00:00:00Z",
    ...overrides,
  }
}

interface HarnessProps {
  initialDevices?: PushSubscriptionDevice[]
  vapidPublicKey?: string
}

function Harness({ initialDevices = [], vapidPublicKey = "vapid-key" }: HarnessProps) {
  const [devices, setDevices] = useState(initialDevices)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      {error && <div data-testid="error">{error}</div>}
      <PushNotificationsSection
        devices={devices}
        vapidPublicKey={vapidPublicKey}
        onDevicesChange={setDevices}
        onError={setError}
      />
    </>
  )
}

describe("PushNotificationsSection", () => {
  beforeEach(() => {
    enableMock.mockReset()
    disableMock.mockReset()
    isSupportedMock.mockReturnValue(true)
    currentPermissionMock.mockReturnValue("default")
    currentDeviceSuffixMock.mockReset()
    currentDeviceSuffixMock.mockResolvedValue(null)
  })
  afterEach(cleanup)

  test("renders the section heading and the Enable button by default", () => {
    render(<Harness />)
    expect(screen.getByRole("heading", { name: "Push notifications" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /enable push on this device/i })).toBeInTheDocument()
  })

  test("renders nothing at all when vapid key is empty", () => {
    const { container } = render(<Harness vapidPublicKey="" />)
    expect(container.querySelector("section")).toBeNull()
    expect(screen.queryByRole("heading", { name: "Push notifications" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /enable push/i })).not.toBeInTheDocument()
  })

  test("shows the unsupported-browser note when isPushSupported returns false", async () => {
    isSupportedMock.mockReturnValue(false)
    render(<Harness />)
    await waitFor(() => {
      expect(screen.getByText(/Push isn't available in this browser/i)).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: /enable push/i })).not.toBeInTheDocument()
  })

  test("shows the deny recovery copy when permission is denied", async () => {
    currentPermissionMock.mockReturnValue("denied")
    render(<Harness />)
    await waitFor(() => {
      expect(screen.getByText(/blocked in this browser/i)).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: /enable push/i })).not.toBeInTheDocument()
  })

  test("clicking Enable adds the returned device optimistically", async () => {
    enableMock.mockResolvedValueOnce(makeDevice({ id: "device-new", platform: "Firefox on Linux" }))

    render(<Harness />)
    fireEvent.click(screen.getByRole("button", { name: /enable push on this device/i }))

    await waitFor(() => expect(screen.getByText("Firefox on Linux")).toBeInTheDocument())
    expect(enableMock).toHaveBeenCalledWith("vapid-key")
  })

  test("clicking Disable on the current device flags isCurrentDevice and removes the row", async () => {
    disableMock.mockResolvedValueOnce(undefined)
    currentDeviceSuffixMock.mockResolvedValue("…end/abc123")
    render(<Harness initialDevices={[makeDevice({ id: "device-1", endpoint_suffix: "…end/abc123" })]} />)

    await waitFor(() => expect(screen.getByText("This device")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: /disable/i }))

    await waitFor(() => expect(screen.queryByText("Chrome on macOS")).not.toBeInTheDocument())
    expect(disableMock).toHaveBeenCalledWith("device-1", { isCurrentDevice: true })
  })

  test("clicking Disable on a non-current device flags isCurrentDevice=false so the local browser isn't unsubscribed", async () => {
    // The bug: pushSubscription.disable used to always unsubscribe the local
    // pushManager, even when the row being deleted belonged to a different
    // device. That left the current browser broken when disabling a phone.
    disableMock.mockResolvedValueOnce(undefined)
    currentDeviceSuffixMock.mockResolvedValue("…this-browser")
    render(
      <Harness
        initialDevices={[
          makeDevice({ id: "device-laptop", platform: "Chrome on macOS", endpoint_suffix: "…this-browser" }),
          makeDevice({ id: "device-phone", platform: "Chrome on Android", endpoint_suffix: "…the-phone" }),
        ]}
      />
    )

    await waitFor(() => expect(screen.getByText("This device")).toBeInTheDocument())
    // The phone's Disable is the second one in DOM order.
    const disableButtons = screen.getAllByRole("button", { name: /disable/i })
    fireEvent.click(disableButtons[1])

    await waitFor(() => expect(disableMock).toHaveBeenCalledWith("device-phone", { isCurrentDevice: false }))
    // Laptop row (this device) still present after the phone was disabled.
    expect(screen.getByText("Chrome on macOS")).toBeInTheDocument()
  })

  test("disable failure restores the device and surfaces an error", async () => {
    disableMock.mockRejectedValueOnce(new Error("network down"))
    render(<Harness initialDevices={[makeDevice({ id: "device-1" })]} />)

    fireEvent.click(screen.getByRole("button", { name: /disable/i }))

    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("network down"))
    // The optimistic removal was reverted because the server rejected.
    expect(screen.getByText("Chrome on macOS")).toBeInTheDocument()
  })

  test("marks 'This device' and hides Enable button when the current browser is in the list", async () => {
    currentDeviceSuffixMock.mockResolvedValue("…end/abc123")
    render(<Harness initialDevices={[makeDevice({ id: "device-1", endpoint_suffix: "…end/abc123" })]} />)

    await waitFor(() => expect(screen.getByText("This device")).toBeInTheDocument())
    expect(screen.queryByRole("button", { name: /enable push on this device/i })).not.toBeInTheDocument()
    expect(screen.getByText(/open this page on it/i)).toBeInTheDocument()
  })

  test("keeps the Enable button when the browser has a subscription not matching any row", async () => {
    // Server lost the row (e.g., stale cleanup) but the browser still thinks
    // it's subscribed. We should still offer Enable so the user can re-register.
    currentDeviceSuffixMock.mockResolvedValue("…orphaned-sub")
    render(<Harness initialDevices={[makeDevice({ id: "device-1", endpoint_suffix: "…end/abc123" })]} />)

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /enable push on this device/i })).toBeInTheDocument()
    )
    expect(screen.queryByText("This device")).not.toBeInTheDocument()
  })
})
