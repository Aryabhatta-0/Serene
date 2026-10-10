import { redirect } from "next/navigation";

// Today is the front door; the shell has no separate home surface.
export default function Home() {
  redirect("/today");
}
