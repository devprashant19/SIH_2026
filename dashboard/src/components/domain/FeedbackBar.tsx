import { useState } from "react";
import { Button } from "@/components/ui/primitives";
import { useFeedbackMutation } from "@/api/hooks";
import { useUiStore } from "@/state/uiStore";
import type { FeedbackDecision } from "@/api/types";

const REVIEWER_KEY = "satsa.reviewer";

function reviewerId(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) || "examiner";
  } catch {
    return "examiner";
  }
}

/** Accept / Reject / Defer with a comment. Keyboard: A, R, D while the bar has focus. */
export function FeedbackBar({ targetType, targetId, status, compact }: { targetType: "finding" | "alert_flag"; targetId: string; status?: FeedbackDecision | null; compact?: boolean }) {
  const [note, setNote] = useState("");
  const [reviewer, setReviewer] = useState(reviewerId);
  const mutation = useFeedbackMutation();
  const pushToast = useUiStore((s) => s.pushToast);

  const submit = (decision: FeedbackDecision) => {
    if (decision === "DEFER" && !note.trim()) {
      pushToast("Add a comment before deferring so the next examiner knows why.", "error");
      return;
    }
    try {
      localStorage.setItem(REVIEWER_KEY, reviewer);
    } catch {
      /* storage may be unavailable */
    }
    mutation.mutate(
      { target_type: targetType, target_id: targetId, decision, reviewer_id: reviewer || "examiner", note: note.trim() || undefined },
      {
        onSuccess: () => {
          setNote("");
          pushToast(`Recorded ${decision.toLowerCase()} for ${targetId.slice(0, 12)}`);
        },
        onError: (e) => pushToast(e instanceof Error ? e.message : "Could not record feedback", "error"),
      },
    );
  };

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      onKeyDown={(e) => {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
        const key = e.key.toLowerCase();
        if (key === "a") submit("ACCEPT");
        if (key === "r") submit("REJECT");
        if (key === "d") submit("DEFER");
      }}
      aria-keyshortcuts="a r d"
    >
      <Button variant="primary" disabled={mutation.isPending} onClick={() => submit("ACCEPT")} title="Accept this finding (A)">
        Accept
      </Button>
      <Button disabled={mutation.isPending} onClick={() => submit("REJECT")} title="Reject this finding (R)">
        Reject
      </Button>
      <Button disabled={mutation.isPending} onClick={() => submit("DEFER")} title="Defer with a comment (D)">
        Defer
      </Button>
      <input
        className="min-w-[180px] flex-1 rounded-sm border border-border bg-bg px-2 py-1 text-sm"
        placeholder="Comment (required to defer)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        aria-label="Feedback comment"
      />
      {!compact && (
        <input
          className="w-28 rounded-sm border border-border bg-bg px-2 py-1 text-sm"
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          aria-label="Reviewer id"
          title="Reviewer id recorded with the decision"
        />
      )}
      {status && <span className="text-xs text-muted">Last decision: {status.toLowerCase()}</span>}
    </div>
  );
}
