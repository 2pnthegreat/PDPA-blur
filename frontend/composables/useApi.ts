import { $fetch } from 'ofetch'
import { useRuntimeConfig } from '#imports'
import type { UseFetchOptions } from '#app'

type FetchOptions<T> = UseFetchOptions<T> & {
  path: string
}

export const useApi = async <T>(options: FetchOptions<T>) => {
  const config = useRuntimeConfig()
  const { path, ...rest } = options
  const url = `${config.public.apiBase}${path}`
  return await $fetch<T>(url, rest as Parameters<typeof $fetch>[1])
}
