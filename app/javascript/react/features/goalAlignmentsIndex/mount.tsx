import { mountIsland } from "~/react/shared/mountIsland"
import { GoalAlignmentsIndex } from "./GoalAlignmentsIndex"
import type { GoalAlignmentsIndexProps } from "./types"

function mount() {
  mountIsland<GoalAlignmentsIndexProps>("react-goal-alignments-index", () => <GoalAlignmentsIndex />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
