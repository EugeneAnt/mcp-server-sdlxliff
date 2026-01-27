<script lang="ts">
	import { SvelteSet } from 'svelte/reactivity';
	import {
		sessionIssues,
		skipIssue,
		unskipIssue,
		markIssueApplied,
		exportAsMarkdown,
		exportAsCsv,
		type Issue
	} from '$lib/stores/issues';
	import { applyAllFixes, applySingleFix, isApplyingFixes } from '$lib/services/chatService';

	// Props
	let { hidden = false }: { hidden?: boolean } = $props();

	// Local state
	let expandedTypes = $state(new SvelteSet<string>());
	let showExportMenu = $state(false);
	let qaObservationsExpanded = $state(false);
	let applyingIssueId = $state<string | null>(null);

	// Derived: separate QA observations from actionable suggestions
	const qaObservations = $derived(
		$sessionIssues.filter((i) => i.source_tool === 'qa_check' && !i.suggested_fix && !i.applied)
	);

	const suggestedFixes = $derived(
		$sessionIssues.filter((i) => i.suggested_fix && !i.applied)
	);

	const appliedFixes = $derived($sessionIssues.filter((i) => i.applied));

	// Group suggested fixes by type
	const fixesByType = $derived(
		suggestedFixes.reduce((acc, issue) => {
			const list = acc.get(issue.issue_type) || [];
			list.push(issue);
			acc.set(issue.issue_type, list);
			return acc;
		}, new Map<string, Issue[]>())
	);

	// Group QA observations by check type
	const qaByType = $derived(
		qaObservations.reduce((acc, issue) => {
			const type = issue.issue_type.replace(/^qa_/, '');
			acc.set(type, (acc.get(type) || 0) + 1);
			return acc;
		}, new Map<string, number>())
	);

	const applicableCount = $derived(suggestedFixes.filter((i) => !i.skipped).length);
	const totalSuggestions = $derived(suggestedFixes.length);

	function toggleType(type: string) {
		if (expandedTypes.has(type)) {
			expandedTypes.delete(type);
		} else {
			expandedTypes.add(type);
		}
	}

	function toggleSkip(issue: Issue) {
		if (issue.skipped) {
			unskipIssue(issue.id);
		} else {
			skipIssue(issue.id);
		}
	}

	async function handleApplySingle(issue: Issue) {
		applyingIssueId = issue.id;
		try {
			await applySingleFix(issue);
		} finally {
			applyingIssueId = null;
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

		try {
			await navigator.clipboard.writeText(content);
			alert(`Copied ${format.toUpperCase()} to clipboard!\n\nFilename suggestion: ${filename}`);
		} catch {
			console.log(`=== ${filename} ===\n${content}`);
			alert('Export copied to console (clipboard failed)');
		}
		showExportMenu = false;
	}
</script>

<div class="w-80 flex flex-col bg-zinc-850 shrink-0 border-l border-zinc-700" class:hidden>
	<!-- Header -->
	<div class="flex items-center justify-between px-4 py-3 bg-zinc-800 border-b border-zinc-700">
		<span class="text-sm font-medium text-zinc-400 uppercase tracking-wide">
			Issues
			{#if totalSuggestions > 0 || qaObservations.length > 0}
				<span class="text-zinc-500">
					({applicableCount} fix{applicableCount !== 1 ? 'es' : ''})
				</span>
				{#if appliedFixes.length > 0}
					<span class="text-green-500 text-xs ml-1">✓{appliedFixes.length}</span>
				{/if}
			{/if}
		</span>

		{#if totalSuggestions > 0 || qaObservations.length > 0}
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
		</div>
	{/if}

	<!-- Content -->
	<div class="flex-1 overflow-y-auto">
		{#if totalSuggestions === 0 && qaObservations.length === 0}
			<div class="flex items-center justify-center h-full text-zinc-600 text-sm px-4 text-center">
				No issues found yet.<br />
				<span class="text-zinc-700 text-xs mt-1">Run QA or review segments to populate.</span>
			</div>
		{:else}
			<!-- QA Observations Section (collapsible reference) -->
			{#if qaObservations.length > 0}
				<div class="border-b border-zinc-600">
					<button
						onclick={() => (qaObservationsExpanded = !qaObservationsExpanded)}
						class="w-full flex items-center gap-2 px-4 py-2 bg-orange-900/20 hover:bg-orange-900/30 transition-colors text-left"
					>
						<span
							class="text-orange-500 transition-transform {qaObservationsExpanded ? 'rotate-90' : ''}"
						>
							<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="9 18 15 12 9 6"></polyline>
							</svg>
						</span>
						<span class="flex-1 text-sm font-medium text-orange-400">
							QA Observations
						</span>
						<span class="text-xs text-orange-500/70">
							{qaObservations.length}
						</span>
					</button>

					{#if qaObservationsExpanded}
						<div class="px-4 py-2 bg-zinc-900/50 text-xs space-y-1">
							<p class="text-zinc-500 text-[10px] mb-2">
								Reference only - LLM reviews these to create suggested fixes
							</p>
							{#each [...qaByType.entries()] as [type, count]}
								<div class="flex justify-between text-zinc-500">
									<span class="capitalize">{type.replace(/_/g, ' ')}</span>
									<span class="text-orange-500/70">{count}</span>
								</div>
							{/each}
							<div class="mt-2 pt-2 border-t border-zinc-800">
								{#each qaObservations.slice(0, 5) as obs}
									<div class="text-zinc-600 py-1 border-b border-zinc-800/50 last:border-0">
										<span class="text-zinc-500">Seg {obs.segment_id}:</span>
										{obs.message.length > 60 ? obs.message.slice(0, 60) + '...' : obs.message}
									</div>
								{/each}
								{#if qaObservations.length > 5}
									<div class="text-zinc-600 text-[10px] mt-1">
										...and {qaObservations.length - 5} more
									</div>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/if}

			<!-- Suggested Fixes Section (actionable) -->
			{#if totalSuggestions > 0}
				{#each [...fixesByType.entries()] as [type, issues]}
					{@const pendingInType = issues.filter((i) => !i.skipped).length}
					<div class="border-b border-zinc-700/50">
						<!-- Type Header -->
						<button
							onclick={() => toggleType(type)}
							class="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-zinc-800/50 transition-colors text-left"
						>
							<span
								class="text-zinc-500 transition-transform {expandedTypes.has(type) ? 'rotate-90' : ''}"
							>
								<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
										class="bg-zinc-900/50 rounded p-2 text-xs {issue.skipped ? 'opacity-40' : ''}"
									>
										<div class="flex items-center justify-between mb-1">
											<span class="text-zinc-300 font-medium">
												Seg {issue.segment_id}
											</span>
											<div class="flex items-center gap-1">
												<span
													class="px-1.5 py-0.5 rounded text-[10px] {getSeverityColor(issue.severity)}"
												>
													{issue.severity}
												</span>
											</div>
										</div>

										<p class="text-zinc-400 mb-1 {issue.skipped ? 'line-through' : ''}">
											{issue.message}
										</p>

										{#if issue.suggested_fix && !issue.skipped}
											<div class="text-green-400/70 mt-1 text-[10px] break-all bg-green-900/10 rounded p-1.5">
												<span class="text-green-600">Fix:</span>
												{issue.suggested_fix.length > 120
													? issue.suggested_fix.slice(0, 120) + '...'
													: issue.suggested_fix}
											</div>
										{/if}

										<!-- Action buttons -->
										<div class="flex items-center justify-end gap-2 mt-2 pt-1.5 border-t border-zinc-800">
											<button
												onclick={() => toggleSkip(issue)}
												class="text-[10px] px-2 py-0.5 rounded transition-colors
													{issue.skipped
														? 'text-zinc-500 bg-zinc-800 hover:bg-zinc-700'
														: 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'}"
											>
												{issue.skipped ? 'Unskip' : 'Skip'}
											</button>
											{#if !issue.skipped}
												<button
													onclick={() => handleApplySingle(issue)}
													disabled={applyingIssueId === issue.id}
													class="text-[10px] px-2 py-0.5 rounded transition-colors
														{applyingIssueId === issue.id
															? 'text-zinc-500 bg-zinc-800 cursor-wait'
															: 'text-green-400 bg-green-900/30 hover:bg-green-900/50'}"
												>
													{applyingIssueId === issue.id ? '...' : 'Apply'}
												</button>
											{/if}
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			{:else if qaObservations.length > 0}
				<!-- Only QA observations, no suggestions yet -->
				<div class="flex items-center justify-center py-8 text-zinc-600 text-sm px-4 text-center">
					<div>
						<p class="text-zinc-500">No suggested fixes yet</p>
						<p class="text-zinc-700 text-xs mt-1">
							Ask LLM to review the QA findings above
						</p>
					</div>
				</div>
			{/if}

			<!-- Applied Section -->
			{#if appliedFixes.length > 0}
				<div class="border-t border-zinc-700 mt-2">
					<div class="px-4 py-2 text-xs text-zinc-600">
						<span class="text-green-600">✓ Applied ({appliedFixes.length})</span>
						<div class="mt-1 space-y-0.5">
							{#each appliedFixes.slice(0, 3) as fix}
								<div class="text-zinc-700 truncate">
									Seg {fix.segment_id}: {fix.message.slice(0, 40)}...
								</div>
							{/each}
							{#if appliedFixes.length > 3}
								<div class="text-zinc-700">...and {appliedFixes.length - 3} more</div>
							{/if}
						</div>
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>
