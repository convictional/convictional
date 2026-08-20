export interface MeetingsIndexProps {
  // When set, the list renders a single collection (editable header + that
  // collection's meetings). When null, it renders a pseudo-collection and
  // `uncategorized` picks between "Most Recent" and "Uncategorized".
  collectionId: string | null
  uncategorized: boolean
  collectionsIndexUrl: string
}
