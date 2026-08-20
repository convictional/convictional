import { type ButtonHTMLAttributes, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react"

// Delay showing the spinner so it doesn't flash on fast requests. Matches the
// 250ms used in the Jinja `submit_button` macro.
const SPINNER_DELAY_MS = 250

interface SubmitButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type" | "onClick"> {
  submitting?: boolean
  className?: string
  children: ReactNode
}

export function SubmitButton({
  submitting = false,
  className = "btn btn-primary",
  disabled,
  children,
  ...rest
}: SubmitButtonProps) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [isFormValid, setIsFormValid] = useState(true)
  const [showSpinner, setShowSpinner] = useState(false)

  // Run the initial validity check before paint so forms with empty required
  // fields don't flash an enabled button for one frame.
  useLayoutEffect(() => {
    const form = buttonRef.current?.form
    if (!form) return
    const check = () => setIsFormValid(form.checkValidity())
    check()
  }, [])

  useEffect(() => {
    const form = buttonRef.current?.form
    if (!form) return

    const check = () => setIsFormValid(form.checkValidity())
    form.addEventListener("input", check)
    form.addEventListener("change", check)
    form.addEventListener("reset", check)
    return () => {
      form.removeEventListener("input", check)
      form.removeEventListener("change", check)
      form.removeEventListener("reset", check)
    }
  }, [])

  useEffect(() => {
    if (!submitting) return
    const timer = setTimeout(() => setShowSpinner(true), SPINNER_DELAY_MS)
    return () => {
      clearTimeout(timer)
      setShowSpinner(false)
    }
  }, [submitting])

  const isDisabled = submitting || !isFormValid || disabled
  const stateClasses = [
    isDisabled ? "cursor-not-allowed btn-disabled" : "",
    showSpinner ? "loading loading-sm loading-spinner" : "",
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <button
      ref={buttonRef}
      type="submit"
      className={`${className} ${stateClasses}`.trim()}
      aria-busy={submitting}
      {...rest}
      disabled={isDisabled}
      onClick={e => {
        const form = e.currentTarget.form
        if (!form) return
        e.preventDefault()
        e.stopPropagation()
        if (form.checkValidity()) {
          form.requestSubmit()
        } else {
          form.reportValidity()
        }
      }}
    >
      {children}
    </button>
  )
}
