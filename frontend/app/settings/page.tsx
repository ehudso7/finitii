"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, isApiError, hasToken, clearToken } from "@/lib/api";
import { TID } from "@/lib/testids";
import { ErrorBox } from "@/components/ErrorBox";

export default function SettingsPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!hasToken()) { router.replace("/login"); }
  }, [router]);

  async function handleExport() {
    setError("");
    setRequestId(null);
    setExporting(true);
    try {
      const { data } = await api.get("/user/export");
      // Create a downloadable blob
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      setExportUrl(url);

      // Trigger download
      const a = document.createElement("a");
      a.href = url;
      a.download = "finitii-export.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      if (isApiError(err)) {
        setError(err.message);
        setRequestId(err.requestId);
      } else {
        setError("Export failed");
      }
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    setError("");
    setRequestId(null);
    setDeleting(true);
    try {
      await api.delete("/user/delete");
      clearToken();
      router.push("/login");
    } catch (err) {
      if (isApiError(err)) {
        setError(err.message);
        setRequestId(err.requestId);
      } else {
        setError("Delete failed");
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      {/* Nav */}
      <nav className="flex gap-4 mb-8 border-b pb-4">
        <Link href="/home" data-testid={TID.navHome} className="text-gray-600 hover:text-gray-900">Home</Link>
        <Link href="/settings" data-testid={TID.navSettings} className="font-semibold text-blue-600">Settings</Link>
      </nav>

      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <ErrorBox message={error} requestId={requestId} />

      {/* Export */}
      <div className="bg-white rounded shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Export Data</h2>
        <button
          data-testid={TID.settingsExport}
          onClick={handleExport}
          disabled={exporting}
          className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {exporting ? "Exporting..." : "Export data"}
        </button>
        {exportUrl && (
          <a
            data-testid={TID.settingsExportDownload}
            href={exportUrl}
            download="finitii-export.json"
            className="ml-4 text-blue-600 underline"
          >
            Download
          </a>
        )}
      </div>

      {/* Delete */}
      <div className="bg-white rounded shadow p-6">
        <h2 className="text-lg font-semibold mb-4 text-red-600">Danger Zone</h2>
        {!confirmDelete ? (
          <button
            data-testid={TID.settingsDelete}
            onClick={() => setConfirmDelete(true)}
            className="bg-red-600 text-white rounded px-4 py-2"
          >
            Delete account
          </button>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-red-600">This action is irreversible. All your data will be deleted.</p>
            <button
              data-testid={TID.settingsDeleteConfirm}
              onClick={handleDelete}
              disabled={deleting}
              className="bg-red-700 text-white rounded px-4 py-2 disabled:opacity-50"
            >
              {deleting ? "Deleting..." : "Confirm delete"}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="ml-2 text-gray-600 underline text-sm"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
