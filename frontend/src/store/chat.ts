import { create } from "zustand";
import { persist } from "zustand/middleware";

type ChatState = {
  conversationId: string;
  setConversationId: (id: string) => void;
  newConversation: () => string;
};

const makeId = () => `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      conversationId: makeId(),
      setConversationId: (conversationId) => set({ conversationId }),
      newConversation: () => {
        const conversationId = makeId();
        set({ conversationId });
        return conversationId;
      },
    }),
    { name: "mh-chat" },
  ),
);
