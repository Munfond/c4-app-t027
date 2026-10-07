import { redirect } from "next/navigation";

export const metadata = { title: "Sensor Agent" };

export default function AgentPage() {
  redirect("/carla");
}
