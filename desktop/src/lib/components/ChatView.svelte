<script lang="ts">
	import { displayMessages, isLoading, shouldAutoScroll, inputValue } from '$lib/stores/chat';
	import { mcpConnected, mcpError } from '$lib/stores/mcp';
	import { selectedPaths } from '$lib/stores/files';
	import { sendMessage } from '$lib/services/chatService';
	import QuickActions from './QuickActions.svelte';

	// Svelte 5: $state() for local reactive state
	let messagesContainer = $state<HTMLDivElement | null>(null);
	let lastMessageCount = $state(0);

	// Svelte 5: $derived() for computed values
	const hasFile = $derived($selectedPaths.length > 0);

	function handleScroll() {
		if (!messagesContainer) return;
		const { scrollTop, scrollHeight, clientHeight } = messagesContainer;
		shouldAutoScroll.set(scrollHeight - scrollTop - clientHeight < 100);
	}

	// Export scroll function for external use
	export function scrollToBottom() {
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	}

	// Svelte 5: $effect() for side effects (auto-scroll on new messages)
	$effect(() => {
		if (messagesContainer && $displayMessages.length > lastMessageCount) {
			lastMessageCount = $displayMessages.length;
			if ($shouldAutoScroll) {
				setTimeout(() => {
					if (messagesContainer) {
						messagesContainer.scrollTop = messagesContainer.scrollHeight;
					}
				}, 0);
			}
		}
	});

	// Handle quick action selection
	function handleQuickAction(event: CustomEvent<string>) {
		inputValue.set(event.detail);
		sendMessage();
	}
</script>

<div bind:this={messagesContainer} onscroll={handleScroll} class="flex-1 overflow-y-auto p-4">
	{#if $displayMessages.length === 0}
		<div class="text-center text-zinc-500 mt-12">
			{#if hasFile}
				<p class="text-zinc-400">What would you like to do?</p>
				<QuickActions on:select={handleQuickAction} />
				<p class="text-xs text-zinc-600 mt-6">Or type your own request below</p>
			{:else}
				<p>Start a conversation to translate and edit SDLXLIFF files.</p>
				<p class="text-sm text-zinc-600 mt-2">Select a file first, then choose an action or type your request.</p>
			{/if}
			{#if !$mcpConnected && $mcpError}
				<p class="text-sm text-red-400 mt-4">MCP Error: {$mcpError}</p>
			{/if}
		</div>
	{/if}

	{#each $displayMessages as message}
		<div class="mb-4 flex flex-col {message.role === 'user' ? 'items-end' : 'items-start'}">
			<div class="max-w-[85%] px-4 py-3 rounded-2xl whitespace-pre-wrap break-words text-[15px] leading-relaxed
				{message.role === 'user' ? 'bg-blue-500 text-white rounded-br-sm' : 'bg-zinc-700 rounded-bl-sm'}
				{message.isStreaming ? 'border-r-2 border-blue-500 animate-pulse' : ''}"
			>
				{message.content}
			</div>
		</div>
	{/each}

	{#if $isLoading && $displayMessages[$displayMessages.length - 1]?.role === 'user'}
		<div class="mb-4 flex flex-col items-start">
			<div class="bg-zinc-700 px-4 py-4 rounded-2xl rounded-bl-sm flex gap-1.5">
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.32s"></span>
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.16s"></span>
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce"></span>
			</div>
		</div>
	{/if}
</div>