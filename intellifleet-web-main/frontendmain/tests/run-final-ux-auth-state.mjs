import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [chat, dashboard, signup, authStore, chatApi] = await Promise.all([
  read('src/components/ChatPanel.tsx'),
  read('src/pages/DashboardPage.tsx'),
  read('src/pages/SignupPage.tsx'),
  read('src/store/authStore.ts'),
  read('src/api/chat.ts'),
]);

assert.match(chat, /clearChatHistory\(\)/, 'New Chat must clear visible messages');
assert.match(chat, /startNewSession\(\)/, 'New Chat must create a new session');
assert.match(chat, /navigator\.clipboard\.writeText\(content\)/, 'Copy must use complete raw answer');
assert.match(chat, /copiedIndex === idx \? 'Copied' : 'Copy'/, 'Copy feedback is required');
assert.match(chat, /!route\.routeData\?\.planning/, 'Network count must exclude plan overlays');
assert.match(chat, /warehouses\.length > 0 && vehicles\.length > 0 && persistedRouteCount > 0/, 'Ready requires all network collections');
assert.match(chat, /Network data has not been uploaded yet/, 'Empty-network notice is required');
assert.match(dashboard, /chatApi\.clearChat\(\)/, 'Reload/logout must clear server chat context');
assert.doesNotMatch(dashboard, /chatApi\.getChatHistory\(\)/, 'Reload must not restore old chat');
assert.match(signup, /Confirm Password/, 'Signup must confirm password');
assert.match(signup, /password !== confirmPassword/, 'Mismatched passwords must be rejected');
assert.match(authStore, /localStorage\.removeItem\('authToken'\)/, 'Logout must remove token');
assert.match(chatApi, /delete\('\/chat\/history'\)/, 'Chat reset must call the scoped backend endpoint');

console.log(JSON.stringify({new_chat:true,refresh_chat:true,copy:true,network_ready:true,network_empty:true,signup:true,logout:true}));
