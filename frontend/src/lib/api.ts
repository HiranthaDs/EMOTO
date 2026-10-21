export type User = { id:number; email:string; full_name:string; role:string }
let csrf = sessionStorage.getItem('emoto_csrf') || ''
export const setCsrf = (value:string) => { csrf=value; sessionStorage.setItem('emoto_csrf', value) }

export async function api<T=unknown>(path:string, init:RequestInit={}):Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type','application/json')
  if (csrf && !['GET','HEAD'].includes((init.method || 'GET').toUpperCase())) headers.set('X-CSRF-Token',csrf)
  const res = await fetch(`/api/v1${path}`, {...init, headers, credentials:'include'})
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(()=>({detail:'Request failed'}))
  if (!res.ok) throw new Error(body.detail || 'Request failed')
  return body
}

export const money = (cents:number|null|undefined) => cents == null ? 'Restricted' : new Intl.NumberFormat('en-LK',{style:'currency',currency:'LKR'}).format(cents/100)
export const dateTime = (value:string) => new Intl.DateTimeFormat('en-LK',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Colombo'}).format(new Date(value))

