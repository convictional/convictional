import { useMemo, useRef, useState } from "react"

import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { ChatsListSkeleton } from "./ChatsListSkeleton"
import { ChatFirstRun } from "./components/ChatFirstRun"
import { ChatItem } from "./components/ChatItem"
import { ChatSearchInput } from "./components/ChatSearchInput"
import { ChatsHeader } from "./components/ChatsHeader"
import { ComposeAction } from "./components/ComposeAction"
import { ContactItem } from "./components/ContactItem"
import { useChatsData } from "./hooks/useChatsData"

export function ChatsIndex() {
  const { user } = useCurrentUser()
  const currentUserId = user?.id ?? null
  const organizationId = user?.organization_id ?? null
  const isMobile = useIsMobile()
  const {
    chats,
    contacts,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    searchQuery,
    setSearchQuery,
    groupFilter,
    setGroupFilter,
    visibleItems,
    selectableItems,
    selectedIndex,
    hoveredIndex,
    setHoveredIndex,
    navigating,
    navigatingId,
    createError,
    selectChat,
    selectContact,
    createGroupAndOpen,
    inviteTeammate,
    handleKeyDown,
    composing,
    selectedRecipients,
    toggleRecipient,
    removeRecipient,
    existingMatchGroup,
    lookupError,
    createChat,
    toggleComposeMode,
  } = useChatsData(organizationId, currentUserId)

  const [inputFocused, setInputFocused] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const selectedRecipientIds = useMemo(() => new Set(selectedRecipients.map(r => r.id)), [selectedRecipients])

  // The first user in an org has no groups and no teammates — only a note-to-self. Surface the
  // create-a-group nudge in that state; it drops away once a real chat or contact exists.
  const hasOnlySelf = chats.every(c => c.type === "self") && contacts.every(c => c.type === "self")
  // Also shown in compose mode: a solo user who clicked "New chat" has no one to add, so the
  // create-a-group / invite first-run is the useful next step there too. Hidden once they type.
  const showFirstRun = groupFilter === "all" && !searchQuery.trim() && hasOnlySelf

  return (
    <div>
      <ChatsHeader
        groupFilter={groupFilter}
        onGroupFilterChange={setGroupFilter}
        composing={composing}
        onToggleCompose={() => {
          toggleComposeMode()
          requestAnimationFrame(() => searchInputRef.current?.focus())
        }}
      >
        <ChatSearchInput
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onKeyDown={handleKeyDown}
          composing={composing}
          selectedRecipients={selectedRecipients}
          onRemoveRecipient={removeRecipient}
          inputFocused={inputFocused}
          onFocusChange={setInputFocused}
          inputRef={searchInputRef}
          autoFocus={!isMobile}
        />
      </ChatsHeader>
      <div className="px-2">
        {createError && <div className="mb-2 px-3 py-2 text-sm text-error bg-error/10 rounded-lg">{createError}</div>}
        {composing && lookupError && (
          <div className="mb-2 px-3 py-2 text-sm text-warning bg-warning/10 rounded-lg">
            Couldn't check for existing conversations. You can still create a new one.
          </div>
        )}
        {loading ? (
          <ChatsListSkeleton />
        ) : error ? (
          <ErrorState message="Failed to load chats. Please try refreshing the page." />
        ) : showFirstRun ? (
          // First user in the org: the first-run is the whole screen (no self row or Contacts
          // divider underneath), matching the chat-show empty state.
          <ChatFirstRun onCreateGroup={createGroupAndOpen} onInvite={inviteTeammate} />
        ) : selectableItems.length === 0 ? (
          <>
            {searchQuery.trim() ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="material-symbols-outlined text-4xl text-base-400 mb-2">search_off</span>
                <p className="text-base-500 text-sm">No results match your search</p>
              </div>
            ) : composing ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="material-symbols-outlined text-4xl text-base-400 mb-2">group_add</span>
                <p className="text-base-500 text-sm">All contacts selected</p>
              </div>
            ) : groupFilter === "groups" ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="material-symbols-outlined text-4xl text-base-400 mb-2">group</span>
                <p className="text-base-500 text-sm">No group chats yet</p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="material-symbols-outlined text-4xl text-base-400 mb-2">group</span>
                <p className="text-base-500 text-sm">No one else in your organization yet</p>
              </div>
            )}
          </>
        ) : (
          <div id="chat-list" onMouseLeave={() => setHoveredIndex(null)}>
            {(() => {
              let selectableIdx = 0
              return visibleItems.map(item => {
                if (item.kind === "contact-divider") {
                  return (
                    <div key="contacts-divider" className="divider text-xs text-base-500 my-2">
                      Contacts
                    </div>
                  )
                }

                const idx = selectableIdx++

                if (item.kind === "compose-looking-up") {
                  return <ComposeAction key="compose-action" />
                }

                if (item.kind === "compose-create") {
                  return (
                    <button
                      key="compose-create"
                      type="button"
                      onClick={createChat}
                      onMouseEnter={() => setHoveredIndex(idx)}
                      className={`flex items-center gap-2 pl-2 pr-3 py-2.5 rounded-lg hover:bg-base-200 transition-colors duration-75 text-left cursor-pointer w-full ${
                        hoveredIndex === idx ? "bg-base-200" : ""
                      } ${navigating ? "opacity-50 pointer-events-none" : ""}`}
                    >
                      <div className="w-3 flex items-center justify-center shrink-0">
                        {selectedIndex === idx && inputFocused && (
                          <div className="w-1.5 h-5 bg-primary rounded-full @mobile:hidden" />
                        )}
                      </div>
                      <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <span className="material-symbols-outlined text-primary text-[14px]">add</span>
                      </div>
                      <span className="text-sm font-medium flex-1">Create chat</span>
                      {navigating ? (
                        <span className="loading loading-spinner loading-xs shrink-0" />
                      ) : (
                        selectedIndex === idx &&
                        inputFocused && (
                          <span className="shrink-0 text-sm text-primary-themed @mobile:hidden">
                            <kbd className="kbd kbd-sm kbd-primary">↵</kbd> create
                          </span>
                        )
                      )}
                    </button>
                  )
                }

                if (item.kind === "compose-match") {
                  return (
                    <ChatItem
                      key={`compose-match:${item.chat.id}`}
                      chat={item.chat}
                      isSelected={selectedIndex === idx}
                      isHovered={hoveredIndex === idx}
                      isNavigating={navigating && navigatingId === item.chat.id}
                      navigatingDisabled={navigating}
                      inputFocused={inputFocused}
                      onSelect={() => selectChat(item.chat.id)}
                      onHover={() => setHoveredIndex(idx)}
                    />
                  )
                }

                if (item.kind === "compose-match-group") {
                  if (!existingMatchGroup) return null
                  const groupChat = {
                    id: existingMatchGroup.id,
                    type: "group" as const,
                    name: existingMatchGroup.name,
                    collaborator_count: 0,
                    collaborators: null,
                    latest_message: null,
                    user: null,
                    picture: null,
                    is_unread: false,
                    is_archived: false,
                    snoozed_until: null,
                  }
                  return (
                    <ChatItem
                      key="compose-match-group"
                      chat={groupChat}
                      isSelected={selectedIndex === idx}
                      isHovered={hoveredIndex === idx}
                      isNavigating={navigating && navigatingId === existingMatchGroup.id}
                      navigatingDisabled={navigating}
                      inputFocused={inputFocused}
                      onSelect={() => selectContact(existingMatchGroup.id, "group")}
                      onHover={() => setHoveredIndex(idx)}
                    />
                  )
                }

                if (item.kind === "chat") {
                  return (
                    <ChatItem
                      key={`chat:${item.chat.id}`}
                      chat={item.chat}
                      isSelected={selectedIndex === idx}
                      isHovered={hoveredIndex === idx}
                      isNavigating={navigating && navigatingId === item.chat.id}
                      navigatingDisabled={navigating}
                      inputFocused={inputFocused}
                      onSelect={() => selectChat(item.chat.id)}
                      onHover={() => setHoveredIndex(idx)}
                    />
                  )
                }

                return (
                  <ContactItem
                    key={`contact:${item.contact.type}:${item.contact.id}`}
                    contact={item.contact}
                    isSelected={selectedIndex === idx}
                    isHovered={hoveredIndex === idx}
                    isNavigating={navigating && navigatingId === item.contact.id}
                    navigatingDisabled={navigating}
                    isRecipient={selectedRecipientIds.has(item.contact.id)}
                    composing={composing}
                    inputFocused={inputFocused}
                    onSelect={() => {
                      const navigates = item.contact.type === "group" || item.contact.type === "self"
                      if (composing && !navigates) {
                        toggleRecipient({
                          id: item.contact.id,
                          name: item.contact.name,
                          picture: item.contact.picture,
                        })
                      } else {
                        selectContact(item.contact.id, item.contact.type)
                      }
                    }}
                    onHover={() => setHoveredIndex(idx)}
                  />
                )
              })
            })()}
            {hasMore && <LoadMoreSentinel onIntersect={loadMore} loading={loadingMore} />}
          </div>
        )}
      </div>
    </div>
  )
}
