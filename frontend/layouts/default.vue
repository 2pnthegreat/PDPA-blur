<template>
  <div class="min-h-screen bg-slate-950 text-slate-100">
    <header class="border-b border-slate-800 bg-slate-900/70 backdrop-blur px-6 py-4">
      <div class="mx-auto flex max-w-5xl items-center justify-between">
        <h1 class="text-lg font-semibold">PDPA Blur Studio</h1>
        <div class="text-sm text-slate-400">Demo version 0.1.0</div>
      </div>
    </header>
    <main class="mx-auto grid max-w-5xl gap-8 px-6 py-10">
      <slot />
    </main>
  </div>
</template>
