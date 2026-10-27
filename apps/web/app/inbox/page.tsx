import Link from "next/link";

import { ApiDown, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { relative } from "@/lib/format";
import type { Message } from "@/lib/types";

export default async function InboxPage() {
  let messages: Message[];
  try {
    messages = (await api<{ messages: Message[] }>("/api/inbox")).messages;
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <PageTitle title="Inbox" />
      <ul className="card divide-y divide-line">
        {messages.map((message) => (
          <li key={message.id}>
            <Link href={`/inbox/${message.id}`} className="grid gap-1 px-5 py-4 sm:grid-cols-[180px_1fr_72px] sm:items-baseline">
              <div className={`text-sm ${message.unread ? "font-semibold" : "text-muted"}`}>{message.sender_name}</div>
              <div>
                <div className={`text-sm ${message.unread ? "font-medium" : ""}`}>{message.subject}</div>
                <div className="truncate text-sm text-muted">{message.snippet}</div>
              </div>
              <div className="text-xs text-faint sm:text-right">{relative(message.received_at)}</div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
