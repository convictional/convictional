// Starts the Recall.AI calendar OAuth handshake, carrying the notetaker auto-join
// preference the old onboarding stepper collected at connect time. The server bakes
// return_to into loginUrl but not the preference, so it's appended here on click.
// Connect is a full-document navigation (leaves the React island) for the cross-origin
// Google handshake, which is why it isn't owned by useCalendarConnection.
export function connectCalendarWithPreference(loginUrl: string, autoJoin: boolean) {
  const preference = autoJoin ? "all" : "none"
  // loginUrl already carries ?return_to=…, so the preference joins with &.
  window.location.assign(`${loginUrl}&recall_calendar_preference=${preference}`)
}
