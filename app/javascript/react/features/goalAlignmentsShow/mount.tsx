import { mountIsland } from "~/react/shared/mountIsland"
import { GoalAlignmentsShow } from "./GoalAlignmentsShow"
import type { GoalAlignmentsShowProps } from "./types"

function mount() {
  mountIsland<GoalAlignmentsShowProps>("react-goal-alignments-show", props => <GoalAlignmentsShow {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
