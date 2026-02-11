"use client";
import { TID } from "@/lib/testids";

export function ErrorBox({ message, requestId }: { message: string; requestId?: string | null }) {
  if (!message) return null;
  return (
    <div data-testid={TID.errorBox} className="bg-red-50 border border-red-300 rounded p-4 my-4">
      <p data-testid={TID.errorMessage} className="text-red-800 text-sm">{message}</p>
      {requestId && (
        <p className="text-red-500 text-xs mt-1">
          Request ID: <span data-testid={TID.requestId}>{requestId}</span>
        </p>
      )}
    </div>
  );
}
