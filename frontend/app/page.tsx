"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasToken } from "@/lib/api";

export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(hasToken() ? "/home" : "/login");
  }, [router]);
  return null;
}
