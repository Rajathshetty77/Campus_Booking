import CalendarView from "@/views/CalendarView";

// Rendered client-side after the session check, so navigations here may block.
export const instant = false;

export default function Page() {
  return <CalendarView />;
}
