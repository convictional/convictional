import { FloatingPortal, autoUpdate, flip, offset, useFloating } from "@floating-ui/react"
import { type ClipboardEvent, type KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { PaginatedResponse } from "~/react/shared/types"
import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import { EmailAddress } from "~/shared/emailAddress"

const SEARCH_DEBOUNCE_MS = 300
// Delay between blur and committing/hiding so a click on a dropdown option
// lands before the input fires its commit-on-blur logic.
const BLUR_COMMIT_DELAY_MS = 150
const MIN_QUERY_LENGTH = 2
const SEARCH_LIMIT = 10

interface EmailContact {
  id: string
  email: string
  name: string
  photo_url: string | null
}

interface EmailContactsResponse extends PaginatedResponse {
  contacts: EmailContact[]
}

export interface EmailContactsTypeaheadProps {
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
  label?: string
  testId?: string
  useCondensedDisplay?: boolean
  inputId?: string
}

function chipLabel(recipient: EmailAddress, useCondensedDisplay: boolean): string {
  if (useCondensedDisplay) return recipient.name
  const domain = recipient.email.split("@")[1] ?? ""
  return `${recipient.name} (${domain})`
}

function toDisplayList(addresses: EmailAddress[]): string[] {
  return addresses.map(addr => addr.displayName)
}

function parseValue(value: string[]): EmailAddress[] {
  return value.flatMap(entry => EmailAddress.parseList(entry))
}

function dedupe(existing: EmailAddress[], incoming: EmailAddress[]): EmailAddress[] {
  const seen = new Set(existing.map(addr => addr.email.toLowerCase()))
  const result = [...existing]
  for (const candidate of incoming) {
    const key = candidate.email.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(candidate)
  }
  return result
}

export function EmailContactsTypeahead({
  value,
  onChange,
  placeholder,
  label,
  testId,
  useCondensedDisplay = false,
  inputId,
}: EmailContactsTypeaheadProps) {
  const fallbackInputId = useId()
  const resolvedInputId = inputId ?? fallbackInputId
  const listboxId = useId()
  const optionId = (index: number) => `${listboxId}-option-${index}`

  const [inputValue, setInputValue] = useState("")
  const [contacts, setContacts] = useState<EmailContact[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const recipients = parseValue(value)
  const recipientsRef = useRef(recipients)
  useEffect(() => {
    recipientsRef.current = recipients
  })

  const debounceTimerRef = useRef<number | null>(null)
  const blurTimerRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    if (selectedIndex >= 0) optionRefs.current[selectedIndex]?.scrollIntoView({ block: "nearest" })
  }, [selectedIndex])

  const { refs, floatingStyles } = useFloating({
    open: showDropdown,
    placement: "bottom-start",
    middleware: [offset(4), flip()],
    whileElementsMounted: autoUpdate,
  })
  const { setReference, setFloating } = refs

  const clearDebounce = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current)
      debounceTimerRef.current = null
    }
  }, [])

  const clearBlur = useCallback(() => {
    if (blurTimerRef.current !== null) {
      window.clearTimeout(blurTimerRef.current)
      blurTimerRef.current = null
    }
  }, [])

  const hideDropdown = useCallback(() => {
    setShowDropdown(false)
    setSelectedIndex(-1)
    setContacts([])
    clearDebounce()
  }, [clearDebounce])

  useEffect(() => {
    return () => {
      clearDebounce()
      clearBlur()
      abortRef.current?.abort()
    }
  }, [clearDebounce, clearBlur])

  const commitRecipients = useCallback(
    (next: EmailAddress[]) => {
      onChange(toDisplayList(next))
    },
    [onChange]
  )

  const addAddresses = useCallback(
    (addresses: EmailAddress[]) => {
      if (addresses.length === 0) return
      const next = dedupe(recipientsRef.current, addresses)
      if (next.length === recipientsRef.current.length) return
      commitRecipients(next)
    },
    [commitRecipients]
  )

  const removeRecipient = useCallback(
    (index: number) => {
      const next = recipientsRef.current.filter((_, i) => i !== index)
      commitRecipients(next)
    },
    [commitRecipients]
  )

  const searchContacts = useCallback(async (query: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const params = new URLSearchParams({ query, limit: String(SEARCH_LIMIT) })
    try {
      const data = await apiFetch<EmailContactsResponse>(`/api/email_contacts?${params}`, {
        signal: controller.signal,
      })
      setContacts(data.contacts)
      setShowDropdown(data.contacts.length > 0)
      setSelectedIndex(data.contacts.length > 0 ? 0 : -1)
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return
      setContacts([])
      setShowDropdown(false)
    }
  }, [])

  const scheduleSearch = useCallback(
    (query: string) => {
      clearDebounce()
      if (query.length < MIN_QUERY_LENGTH) {
        hideDropdown()
        return
      }
      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = null
        void searchContacts(query)
      }, SEARCH_DEBOUNCE_MS)
    },
    [clearDebounce, hideDropdown, searchContacts]
  )

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const next = event.target.value
      setInputValue(next)

      const trimmed = next.trim()
      if (trimmed.endsWith(",")) {
        const emailText = trimmed.slice(0, -1).trim()
        if (emailText && EmailAddress.isValidEmail(emailText)) {
          addAddresses([EmailAddress.parse(emailText)])
          setInputValue("")
          hideDropdown()
          return
        }
      }

      scheduleSearch(trimmed)
    },
    [addAddresses, hideDropdown, scheduleSearch]
  )

  const selectContact = useCallback(
    (contact: EmailContact) => {
      addAddresses([EmailAddress.build(contact.email, contact.name)])
      setInputValue("")
      hideDropdown()
    },
    [addAddresses, hideDropdown]
  )

  const commitTypedText = useCallback((): boolean => {
    const trimmed = inputValue.trim()
    if (!trimmed || !EmailAddress.isValidEmail(trimmed)) return false
    addAddresses([EmailAddress.parse(trimmed)])
    setInputValue("")
    return true
  }, [addAddresses, inputValue])

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (showDropdown) {
        switch (event.key) {
          case "ArrowDown":
            event.preventDefault()
            setSelectedIndex(prev => Math.min(prev + 1, contacts.length - 1))
            return
          case "ArrowUp":
            event.preventDefault()
            setSelectedIndex(prev => Math.max(prev - 1, -1))
            return
          case "Enter":
          case "Tab":
            if (selectedIndex >= 0 && selectedIndex < contacts.length) {
              event.preventDefault()
              selectContact(contacts[selectedIndex])
            } else if (commitTypedText()) {
              event.preventDefault()
            }
            return
          case "Escape":
            hideDropdown()
            return
        }
        return
      }

      switch (event.key) {
        case "Enter":
        case ",":
          event.preventDefault()
          commitTypedText()
          return
        case "Tab":
          if (commitTypedText()) {
            event.preventDefault()
          }
          return
        case "Backspace":
          if (inputValue === "" && recipientsRef.current.length > 0) {
            removeRecipient(recipientsRef.current.length - 1)
          }
          return
      }
    },
    [commitTypedText, contacts, hideDropdown, inputValue, removeRecipient, selectContact, selectedIndex, showDropdown]
  )

  const handlePaste = useCallback(
    (event: ClipboardEvent<HTMLInputElement>) => {
      const text = event.clipboardData.getData("text")
      if (!text.includes(",")) return
      const parsed = EmailAddress.parseList(text)
      if (parsed.length === 0) return
      event.preventDefault()
      addAddresses(parsed)
      setInputValue("")
      hideDropdown()
    },
    [addAddresses, hideDropdown]
  )

  const handleBlur = useCallback(() => {
    clearBlur()
    blurTimerRef.current = window.setTimeout(() => {
      blurTimerRef.current = null
      commitTypedText()
      hideDropdown()
    }, BLUR_COMMIT_DELAY_MS)
  }, [clearBlur, commitTypedText, hideDropdown])

  // mousedown fires before blur. preventDefault on the dropdown stops the
  // input from losing focus at all, so handleBlur never runs and the click
  // commits cleanly. Belt-and-suspenders: also cancel any pending blur timer.
  const handleDropdownMouseDown = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault()
      clearBlur()
    },
    [clearBlur]
  )

  return (
    <div className="relative w-full">
      <div className="flex items-center gap-3 w-full">
        {label && (
          <label className="text-xs font-semibold text-base-500" htmlFor={resolvedInputId}>
            {label}
          </label>
        )}
        <div className="flex flex-wrap items-center gap-1 flex-1 min-w-0 bg-transparent">
          {recipients.map((recipient, index) => (
            <div
              key={`${recipient.email}-${index}`}
              className="bg-base-200 rounded-lg px-2 py-0 flex items-center gap-1 border border-base-400 shadow-sm"
            >
              <span className="text-xs">{chipLabel(recipient, useCondensedDisplay)}</span>
              <button
                type="button"
                onClick={event => {
                  event.stopPropagation()
                  removeRecipient(index)
                }}
                aria-label={`Remove ${recipient.email}`}
                className="cursor-pointer text-base-500 hover:text-base-700"
              >
                <span className="material-symbols-outlined text-sm -my-1">close</span>
              </button>
            </div>
          ))}
          <input
            ref={setReference}
            id={resolvedInputId}
            data-testid={testId}
            type="text"
            className="input input-sm flex-1 bg-transparent border-0 !rounded-none focus:border-primary focus:outline-none px-0 min-w-[120px]"
            placeholder={recipients.length === 0 ? placeholder : ""}
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            onBlur={handleBlur}
            autoComplete="off"
            role="combobox"
            aria-haspopup="listbox"
            aria-autocomplete="list"
            aria-expanded={showDropdown}
            aria-controls={listboxId}
            aria-activedescendant={selectedIndex >= 0 ? optionId(selectedIndex) : undefined}
          />
        </div>
      </div>
      {showDropdown && (
        <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
          <div
            ref={setFloating}
            id={listboxId}
            role="listbox"
            style={floatingStyles}
            data-dropdown
            onMouseDown={handleDropdownMouseDown}
            className="dropdown-card z-50 max-h-60 overflow-y-auto min-w-content"
          >
            <div className="p-1">
              {contacts.map((contact, index) => (
                <button
                  key={contact.id}
                  ref={el => {
                    optionRefs.current[index] = el
                  }}
                  id={optionId(index)}
                  role="option"
                  aria-selected={selectedIndex === index}
                  type="button"
                  onClick={() => selectContact(contact)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={`dropdown-item pl-1 py-1.5 grid grid-cols-[auto_1fr] gap-2 items-center w-full text-left ${
                    selectedIndex === index ? "bg-base-400 inset-shadow-sm text-base-900" : ""
                  }`}
                >
                  <div className="w-4 h-4 rounded-full bg-base-300 flex items-center justify-center flex-shrink-0">
                    {contact.photo_url ? (
                      <img src={contact.photo_url} alt={contact.name} className="w-4 h-4 rounded-full object-cover" />
                    ) : (
                      <span className="text-sm font-semibold text-base-content/70">
                        {(contact.name || contact.email).charAt(0).toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="grid sm:flex sm:gap-2">
                    {contact.name && <span className="truncate">{contact.name}</span>}
                    <span className="text-base-content/70 truncate">{contact.email}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </FloatingPortal>
      )}
    </div>
  )
}
