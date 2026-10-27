import Link from "next/link";

import { ApiDown, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { Message } from "@/lib/types";

export default async function MessagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let message: Message;
  try {
    message = await api<Message>(`/api/inbox/${id}`);
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <Link href="/inbox" className="text-sm text-muted">
        Inbox
      </Link>
      <PageTitle kicker={`${message.sender_name} · ${message.sender_email}`} title={message.subject} />
      <p className="mb-6 text-sm text-faint">{formatWhen(message.received_at)}</p>
      <article className="card whitespace-pre-wrap p-6 text-[15px] leading-7">{message.body}</article>
    </div>
  );
}
