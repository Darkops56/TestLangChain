let conversationId = null;

async function ensureConversation() {
  if (conversationId) return conversationId;
  const response = await fetch('/api/chat/conversations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ locale: 'es-AR' })
  });
  const payload = await response.json();
  conversationId = payload.conversationId;
  return conversationId;
}

document.getElementById('prompt').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = document.getElementById('msg');
  const text = input.value.trim();
  if (!text) return;

  const id = await ensureConversation();
  const sendResponse = await fetch(`/api/chat/conversations/${id}/messages`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text, locale: 'es-AR' })
  });
  if (!sendResponse.ok) return;
  const payload = await sendResponse.json();

  const chat = document.getElementById('chat');
  const userBubble = document.createElement('article');
  userBubble.className = 'bubble';
  const userParagraph = document.createElement('p');
  userParagraph.textContent = payload.userMessage.content;
  userBubble.appendChild(userParagraph);
  chat.appendChild(userBubble);

  const botBubble = document.createElement('article');
  botBubble.className = 'bubble';
  const botParagraph = document.createElement('p');
  botParagraph.textContent = payload.botMessage.content;
  botBubble.appendChild(botParagraph);
  chat.appendChild(botBubble);

  input.value = '';
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
});
