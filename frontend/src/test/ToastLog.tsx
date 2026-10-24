// For mounted tests: the toasts a component shows, reported as they come
// (the page's toast list isn't mounted there).
import { useEffect } from "react";
import type { Toast } from "../contexts/ToastContext";
import { useToast } from "../contexts/useToast";

export default function ToastLog({ onToasts }: { onToasts: (toasts: Toast[]) => void }) {
  const { toasts } = useToast();
  useEffect(() => onToasts(toasts), [toasts, onToasts]);
  return null;
}
