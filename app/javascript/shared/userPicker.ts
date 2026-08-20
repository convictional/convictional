import { AlpineComponent } from "alpinejs"

interface User {
  id: string
  name: string
}

interface UserSearchFilterProps {
  users: User[]
}

interface SearchFilterData {
  // State
  searchQuery: string
  visibleUserIds: string[]

  // Filter methods
  filterUsers(): void
  resetFilter(): void
  hasNoResults(): boolean
}

function userSearchFilterComponent({ users }: UserSearchFilterProps): AlpineComponent<SearchFilterData> {
  const getFilteredUserIds = (searchQuery: string = ""): string[] => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return users.map(user => user.id)
    }
    return users.filter(user => user.name.trim().toLowerCase().includes(query)).map(user => user.id)
  }

  return {
    // State
    searchQuery: "",
    visibleUserIds: getFilteredUserIds(),

    // Filter methods
    filterUsers() {
      this.visibleUserIds = getFilteredUserIds(this.searchQuery)
    },

    resetFilter() {
      this.searchQuery = ""
      this.visibleUserIds = getFilteredUserIds()
    },

    hasNoResults(): boolean {
      return this.searchQuery !== "" && this.visibleUserIds.length === 0
    },
  }
}

export { userSearchFilterComponent }
export type { User, UserSearchFilterProps, SearchFilterData }
