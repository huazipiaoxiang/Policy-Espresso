import { redirect } from "next/navigation";

// 「总览 Dashboard」已合并进「政策跟进中心」，旧路由跳转过去
export default function RadarPage() {
  redirect("/follow-up");
}
