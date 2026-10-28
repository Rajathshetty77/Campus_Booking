import MyBookingsView from "@/views/MyBookingsView";

// Rendered client-side after the session check, so navigations here may block.
export const instant = false;

export default function Page() {
  return <MyBookingsView />;
}
