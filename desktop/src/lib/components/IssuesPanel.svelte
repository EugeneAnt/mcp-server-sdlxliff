<script lang="ts">
	import {
		sessionIssues,
		skipIssue,
		unskipIssue,
		getApplicableIssues,
		exportAsMarkdown,
		exportAsCsv,
		type Issue
	} from '$lib/stores/issues';
	import { applyAllFixes, isApplyingFixes } from '$lib/services/chatService';

	let expandedTypes: Set<string> = new Set();
	let showExportMenu = false;

	// Group issues by type (exclude applied)
	$: activeIssues = $sessionIssues.filter((i) => !i.applied);
	$: issuesByType = activeIssues.reduce(
		(acc, issue) => {
			const list = acc.get(issue.issue_type) || [];
			list.push(issue);
			acc.set(issue.issue_type, list);
			return acc;
		},
		new Map<string, Issue[]>()
	);

	$: pendingCount = $sessionIssues.filter((i) => !i.skipped && !i.applied).length;
	$: applicableCount = $sessionIssues.filter((i) => !i.skipped && !i.applied && i.suggested_fix).length;
	$: appliedCount = $sessionIssues.filter((i) => i.applied).length;
	$: totalCount = $sessionIssues.length;

	function toggleType(type: string) {
		if (expandedTypes.has(type)) {
			expandedTypes.delete(type);
		} else {
			expandedTypes.add(type);
		}
		expandedTypes = expandedTypes; // trigger reactivity
	}

	function toggleSkip(issue: Issue) {
		if (issue.skipped) {
			unskipIssue(issue.id);
		} else {
			skipIssue(issue.id);
		}
	}

	function formatType(type: string): string {
		return type
			.replace(/^qa_/, '')
			.replace(/_/g, ' ')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	function getSeverityColor(severity: string): string {
		switch (severity) {
			case 'error':
				return 'text-red-400 bg-red-900/30';
			case 'warning':
				return 'text-yellow-400 bg-yellow-900/30';
			case 'info':
				return 'text-blue-400 bg-blue-900/30';
			default:
				return 'text-zinc-400 bg-zinc-800';
		}
	}

	function getTypeColor(type: string): string {
		if (type.startsWith('qa_')) return 'text-orange-400';
		if (type === 'semantic') return 'text-purple-400';
		if (type === 'terminology') return 'text-cyan-400';
		return 'text-zinc-400';
	}

	async function handleExport(format: 'markdown' | 'csv') {
		const content = format === 'markdown' ? exportAsMarkdown() : exportAsCsv();
		const filename = `issues-${new Date().toISOString().slice(0, 10)}.${format === 'markdown' ? 'md' : 'csv'}`;

		// Use clipboard for now (could use Tauri file dialog for save)
		try {
			await navigator.clipboard.writeText(content);
			alert(`Copied ${format.toUpperCase()} to clipboard!\n\nFilename suggestion: ${filename}`);
		} catch {
			// Fallback: show in console
			console.log(`=== ${filename} ===\n${content}`);
			alert('Export copied to console (clipboard failed)');
		}
		showExportMenu = false;
	}
</script>

<div class="w-80 flex flex-col bg-zinc-850 shrink-0 border-l border-zinc-700">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 py-3 bg-zinc-800 border-b border-zinc-700">
		<span class="text-sm font-medium text-zinc-400 uppercase tracking-wide">
			Issues
			{#if totalCount > 0}
				<span class="text-zinc-500">({pendingCount}/{totalCount})</span>
				{#if appliedCount > 0}
					<span class="text-green-500 text-xs ml-1">✓{appliedCount}</span>
				{/if}
			{/if}
		</span>

		{#if totalCount > 0}
			<div class="relative">
				<button
					onclick={() => (showExportMenu = !showExportMenu)}
					class="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-700"
				>
					Export
				</button>
				{#if showExportMenu}
					<div class="absolute right-0 top-full mt-1 bg-zinc-800 border border-zinc-700 rounded shadow-lg z-10">
						<button
							onclick={() => handleExport('markdown')}
							class="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
						>
							Markdown
						</button>
						<button
							onclick={() => handleExport('csv')}
							class="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
						>
							CSV
						</button>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Apply All Button -->
	{#if applicableCount > 0}
		<div class="px-4 py-2 bg-zinc-800/50 border-b border-zinc-700">
			<button
				onclick={applyAllFixes}
				disabled={$isApplyingFixes}
				class="w-full py-2 px-3 text-sm font-medium rounded transition-colors
					{$isApplyingFixes
						? 'bg-zinc-700 text-zinc-500 cursor-wait'
						: 'bg-blue-600 hover:bg-blue-500 text-white'}"
			>
				{#if $isApplyingFixes}
					Applying...
				{:else}
					Apply All Fixes ({applicableCount})
				{/if}
			</button>
			<p class="text-[10px] text-zinc-600 mt-1 text-center">
				Non-skipped issues with suggested fixes
			</p>
		</div>
	{/if}

	<!-- Issues List -->
	<div class="flex-1 overflow-y-auto">
		{#if totalCount === 0}
			<div class="flex items-center justify-center h-full text-zinc-600 text-sm px-4 text-center">
				No issues found yet.<br />
				<span class="text-zinc-700 text-xs mt-1">Run QA or review segments to populate.</span>
			</div>
		{:else}
			{#each [...issuesByType.entries()] as [type, issues]}
				{@const pendingInType = issues.filter((i) => !i.skipped).length}
				<div class="border-b border-zinc-700/50">
					<!-- Type Header -->
					<button
						onclick={() => toggleType(type)}
						class="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-zinc-800/50 transition-colors text-left"
					>
						<span
							class="text-zinc-500 transition-transform {expandedTypes.has(type)
								? 'rotate-90'
								: ''}"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="12"
								height="12"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
							>
								<polyline points="9 18 15 12 9 6"></polyline>
							</svg>
						</span>
						<span class="flex-1 text-sm font-medium {getTypeColor(type)}">
							{formatType(type)}
						</span>
						<span class="text-xs text-zinc-500">
							{pendingInType}/{issues.length}
						</span>
					</button>

					<!-- Issues in Type -->
					{#if expandedTypes.has(type)}
						<div class="px-3 pb-2 space-y-1.5">
							{#each issues as issue}
								<div
									class="bg-zinc-900/50 rounded p-2 text-xs {issue.skipped
										? 'opacity-40'
										: ''}"
								>
									<div class="flex items-center justify-between mb-1">
										<span class="text-zinc-300 font-medium">
											Seg {issue.segment_id}
										</span>
										<div class="flex items-center gap-1.5">
											<span
												class="px-1.5 py-0.5 rounded text-[10px] {getSeverityColor(
													issue.severity
												)}"
											>
												{issue.severity}
											</span>
											<button
												onclick={() => toggleSkip(issue)}
												class="text-zinc-500 hover:text-zinc-300 transition-colors px-1"
												title={issue.skipped ? 'Include in batch apply' : 'Skip this issue'}
											>
												{#if issue.skipped}
													<span class="text-[10px] text-zinc-600">SKIPPED</span>
												{:else}
													<span class="text-[10px]">Skip</span>
												{/if}
											</button>
										</div>
									</div>

									<p class="text-zinc-400 mb-1 {issue.skipped ? 'line-through' : ''}">
										{issue.message}
									</p>

									{#if issue.source}
										<div class="text-zinc-600 truncate" title={issue.source}>
											<span class="text-zinc-700">S:</span>
											{issue.source.length > 50
												? issue.source.slice(0, 50) + '...'
												: issue.source}
										</div>
									{/if}

									{#if issue.suggested_fix && !issue.skipped}
										<div class="text-green-400/70 mt-1 text-[10px] break-all">
											→ {issue.suggested_fix.length > 100
												? issue.suggested_fix.slice(0, 100) + '...'
												: issue.suggested_fix}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</div>