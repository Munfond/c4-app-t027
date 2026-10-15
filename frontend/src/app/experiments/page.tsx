import { redirect } from "next/navigation";

export default function LegacyExperimentPage() {
  redirect("/lab?agent=dataset_replay&tools=history");
}
