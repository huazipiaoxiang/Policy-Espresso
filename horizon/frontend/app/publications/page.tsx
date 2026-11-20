import { redirect } from "next/navigation";

// 「发布中心」已合并进「政策跟进中心」，旧路由跳转过去
export default function PublicationsPage() {
  redirect("/follow-up");
}
