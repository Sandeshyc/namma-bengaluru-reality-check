import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ?? "";

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    [
      "Supabase browser client is misconfigured.",
      "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (Project Settings → API in Supabase).",
      "Do not use the service role key in NEXT_PUBLIC_* variables.",
      "Server-only SUPABASE_URL is not visible to the client unless exposed as NEXT_PUBLIC_SUPABASE_URL.",
    ].join(" "),
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
