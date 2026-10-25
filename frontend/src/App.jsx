import { useCallback, useEffect, useMemo, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { ArrowDown, ArrowRight, CalendarDays, Check, ChevronDown, Compass, Download, Heart, LoaderCircle, LogIn, LogOut, MapPin, Mountain, Plus, RefreshCw, Sparkles, Sun, Trash2, Utensils, WandSparkles, X } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY
const supabase = supabaseUrl && supabaseKey ? createClient(supabaseUrl, supabaseKey) : null
const SLOTS = ['Morning Sightseeing', 'Lunch Recommendation', 'Afternoon Leisure', 'Evening Dining & Entertainment']
const TIMES = ['09:00–12:00', '12:30–14:00', '14:30–17:00', '18:30–21:00']
const INTERESTS = ['Food', 'Adventure', 'History', 'Nightlife']
const VIBES = ['Beach', 'Mountains', 'Cultural', 'Urban']
const BUDGET_LABELS = { Budget: 'Economical', Moderate: 'Moderate', Luxury: 'Luxury' }
const DESTINATION_CURRENCIES = { 'United States': 'USD', 'New York': 'USD', 'Los Angeles': 'USD', 'San Francisco': 'USD', 'Las Vegas': 'USD', 'Chicago': 'USD', 'London': 'GBP', 'United Kingdom': 'GBP', Paris: 'EUR', Lisbon: 'EUR', Rome: 'EUR', Barcelona: 'EUR', Amsterdam: 'EUR', Berlin: 'EUR', Madrid: 'EUR', Athens: 'EUR', Vienna: 'EUR', 'Cape Town': 'ZAR', 'South Africa': 'ZAR', Tokyo: 'JPY', Kyoto: 'JPY', Osaka: 'JPY', Japan: 'JPY', Bangkok: 'THB', Thailand: 'THB', Bali: 'IDR', Jakarta: 'IDR', Indonesia: 'IDR', 'Mexico City': 'MXN', Mexico: 'MXN', Jaipur: 'INR', Goa: 'INR', Mumbai: 'INR', Delhi: 'INR', Bengaluru: 'INR', Kochi: 'INR', Bhopal: 'INR', India: 'INR', Sydney: 'AUD', Melbourne: 'AUD', Australia: 'AUD', Toronto: 'CAD', Vancouver: 'CAD', Canada: 'CAD', Singapore: 'SGD', Dubai: 'AED', 'Abu Dhabi': 'AED', UAE: 'AED', Seoul: 'KRW', 'South Korea': 'KRW', Istanbul: 'TRY', Turkey: 'TRY', Zurich: 'CHF', Switzerland: 'CHF', Beijing: 'CNY', Shanghai: 'CNY', China: 'CNY', Hanoi: 'VND', Vietnam: 'VND', Manila: 'PHP', Philippines: 'PHP', 'Kuala Lumpur': 'MYR', Malaysia: 'MYR', Auckland: 'NZD', 'New Zealand': 'NZD', Stockholm: 'SEK', Sweden: 'SEK', Oslo: 'NOK', Norway: 'NOK', Copenhagen: 'DKK', Denmark: 'DKK', Prague: 'CZK', Czechia: 'CZK', Warsaw: 'PLN', Poland: 'PLN' }
const FALLBACK_USD_RATES = { USD: 1, INR: 94.78, EUR: 0.92, GBP: 0.79, JPY: 150, THB: 36, IDR: 15800, MXN: 17, ZAR: 18.5, AUD: 1.55, CAD: 1.37, SGD: 1.34, AED: 3.67, KRW: 1380, TRY: 32, CHF: 0.9, CNY: 7.2, VND: 25000, PHP: 56, MYR: 4.5, NZD: 1.7, SEK: 10.5, NOK: 10.7, DKK: 6.9, CZK: 23, PLN: 4 }
const DESTINATION_PRICE_FACTORS = { INR: 0.14, THB: 0.42, IDR: 0.4, VND: 0.32, PHP: 0.4, MYR: 0.45, MXN: 0.55, ZAR: 0.6, TRY: 0.5, CNY: 0.65, KRW: 0.75, JPY: 0.85, EUR: 0.95, GBP: 1, USD: 1, AUD: 1, CAD: 1, SGD: 0.9, AED: 0.9, CHF: 1.15, NZD: 0.95, SEK: 1, NOK: 1.05, DKK: 1, CZK: 0.75, PLN: 0.75 }
const DESTINATION_ACTIVITY_FACTORS = { INR: 0.12, THB: 0.24, IDR: 0.22, VND: 0.18, PHP: 0.22, MYR: 0.28, MXN: 0.35, ZAR: 0.4, TRY: 0.35, CNY: 0.45, KRW: 0.6, JPY: 0.75, EUR: 0.8, GBP: 0.9, USD: 1, AUD: 0.9, CAD: 0.9, SGD: 0.75, AED: 0.8, CHF: 1, NZD: 0.85, SEK: 0.85, NOK: 0.9, DKK: 0.85, CZK: 0.55, PLN: 0.55 }
const STAY_AREAS = {
  Goa: ['Panaji city centre', 'Calangute & Candolim', 'Mapusa'],
  Bhopal: ['MP Nagar', 'New Market & TT Nagar', 'Arera Colony'],
  Mumbai: ['Fort & Colaba', 'Bandra', 'Andheri near the metro'],
  Delhi: ['Paharganj near New Delhi Station', 'Karol Bagh', 'South Delhi'],
  Jaipur: ['Bani Park', 'Civil Lines', 'MI Road'],
  Bengaluru: ['Indiranagar', 'MG Road', 'Jayanagar'],
  Kochi: ['Fort Kochi', 'Ernakulam near the metro', 'Mattancherry'],
}
const destinationCurrency = (destination = '') => {
  const city = destination.trim().toLowerCase()
  return DESTINATION_CURRENCIES[destination.trim()] || Object.entries(DESTINATION_CURRENCIES).find(([name]) => city.includes(name.toLowerCase()))?.[1] || 'INR'
}
const destinationMoney = (usd, destination, rates) => {
  const currency = destinationCurrency(destination)
  const converted = Number(usd || 0) * (rates?.[currency] || FALLBACK_USD_RATES[currency] || 1)
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(converted) }
  catch { return `${currency} ${Math.round(converted).toLocaleString()}` }
}
const normalizeStays = (stays, city, budget = 'Moderate') => {
  const area = { Goa: 'Panaji, Candolim, or Calangute', Jaipur: 'Bani Park or Civil Lines', Mumbai: 'Fort or Bandra', Delhi: 'Connaught Place or South Delhi', Bengaluru: 'Indiranagar or MG Road', Kochi: 'Fort Kochi or Ernakulam' }[city] || `${city} city centre`
  const factor = { Budget: 0.72, Moderate: 1, Luxury: 1.75 }[budget] || 1
  const fallback = [['Good-value guesthouse', 55], ['Comfortable boutique stay', 125], ['Special-occasion hotel', 260]]
  const localFactor = DESTINATION_PRICE_FACTORS[destinationCurrency(city)] || 1
  const source = Array.isArray(stays) && stays.length ? stays : fallback.map(([style, nightly]) => ({ style, area, estimated_nightly_usd: nightly * factor * localFactor }))
  return source.map((stay, i) => {
    const tier = fallback[Math.min(i, fallback.length - 1)]
    const style = String(stay?.style || '').trim()
    const stayArea = String(stay?.area || '').trim()
    const cost = Number(stay?.estimated_nightly_usd)
    return {
      ...stay,
      style: !style || style.toLowerCase() === 'stay option' ? tier[0] : style,
      area: !stayArea || stayArea.toLowerCase() === 'central area' ? area : stayArea,
      estimated_nightly_usd: Number.isFinite(cost) && cost > 0 ? cost : Math.round(tier[1] * factor * localFactor),
      why: String(stay?.why || '').trim() || `A suggested area for exploring ${city}; compare current listings, guest reviews, and cancellation terms.`,
    }
  })
}
const normalizeLegacyPlan = (trip, destination) => {
  const preferences = trip.preferences || {}
  if (Number(preferences.price_estimate_version) >= 2) return trip
  const currency_code = preferences.currency_code || destinationCurrency(destination)
  const factor = DESTINATION_PRICE_FACTORS[currency_code] || 1
  const activityFactor = DESTINATION_ACTIVITY_FACTORS[currency_code] || factor * 0.75
  const scale = (value, multiplier = factor) => Math.round((Number(value) || 0) * multiplier * 100) / 100
  return {
    ...trip,
    preferences: { ...preferences, currency_code, price_estimate_version: 2 },
    days: (trip.days || trip.itinerary || []).map((day) => ({ ...day, items: (day.items || []).map((item) => ({ ...item, cost_usd: scale(item.cost_usd, activityFactor) })) })),
    accommodations: (trip.accommodations || []).map((stay) => ({ ...stay, estimated_nightly_usd: scale(stay.estimated_nightly_usd) })),
    transportation: { ...(trip.transportation || {}), daily_transfers: (trip.transportation?.daily_transfers || []).map((transfer) => ({ ...transfer, estimated_transit_usd_per_person: scale(transfer.estimated_transit_usd_per_person) })) },
  }
}

function mapsRouteUrl(day, city) {
  const stops = (day?.items || []).map((item) => `${item.title}, ${city}`).filter(Boolean)
  if (!stops.length) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(city)}`
  const origin = stops[0]
  const destination = stops.at(-1)
  const waypoints = stops.slice(1, -1).join('|')
  return `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}${waypoints ? `&waypoints=${encodeURIComponent(waypoints)}` : ''}&travelmode=transit`
}

function App() {
  const [session, setSession] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [tab, setTab] = useState('Discover')
  const [prefs, setPrefs] = useState({ destination: '', vibe: 'Cultural', duration: 4, start_date: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10), budget: 'Moderate', party: 'Couple', group_size: 2, pace: 'Moderate', interests: ['Food', 'History'] })
  const [plan, setPlan] = useState(null)
  const [saved, setSaved] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [photos, setPhotos] = useState([])
  const [loading, setLoading] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [swapRequest, setSwapRequest] = useState('')
  const [selectedDay, setSelectedDay] = useState(0)
  const [selectedSlot, setSelectedSlot] = useState(0)
  const [showSaved, setShowSaved] = useState(false)
  const [joinCode, setJoinCode] = useState('')
  const [serviceConfig, setServiceConfig] = useState(null)
  const [exchangeRates, setExchangeRates] = useState({})

  const api = useCallback(async (path, options = {}) => {
    const makeRequest = (token) => {
      const headers = { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers }
      return fetch(`${API}${path}`, { ...options, headers })
    }
    let token = session?.access_token
    let response = await makeRequest(token)
    if (response.status === 401 && token && supabase) {
      try {
        const { data, error: refreshError } = await supabase.auth.refreshSession()
        if (refreshError || !data.session?.access_token) throw refreshError || new Error('No active session')
        token = data.session.access_token
        setSession(data.session)
        response = await makeRequest(token)
      } catch {
        setSession(null)
        setAuthMode('signin')
        setAuthOpen(true)
        setAuthMessage('Your sign-in expired. Sign in again to continue editing this trip.')
        throw new Error('Your sign-in expired. Please sign in again to continue.')
      }
    }
    if (!response.ok) {
      let message = `Request failed (${response.status})`
      try { message = (await response.json()).detail || message } catch { /* response may not be JSON */ }
      if (response.status === 401) {
        setAuthMode('signin')
        setAuthOpen(true)
        setAuthMessage('Your sign-in expired. Sign in again to continue editing this trip.')
      }
      throw new Error(message)
    }
    return response.status === 204 ? null : response
  }, [session])

  useEffect(() => {
    let active = true
    fetch('https://api.frankfurter.dev/v2/rates?base=USD')
      .then((response) => response.ok ? response.json() : [])
      .then((rows) => { if (active && Array.isArray(rows)) setExchangeRates(Object.fromEntries(rows.map((row) => [row.quote, row.rate]))) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!supabase) { setAuthReady(true); return }
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setAuthReady(true) })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    fetch(`${API}/api/config`).then((response) => response.ok ? response.json() : null).then(setServiceConfig).catch(() => setServiceConfig(null))
  }, [])

  const loadTrips = useCallback(async () => {
    if (!session) { setSaved([]); return }
    try { const response = await api('/api/trips'); setSaved(await response.json()) } catch (e) { setError(e.message) }
  }, [session, api])
  useEffect(() => { loadTrips() }, [loadTrips])

  const getRecommendations = useCallback(async () => {
    setLoading('recommend'); setError('')
    try {
      const q = new URLSearchParams({ vibe: prefs.vibe, budget: prefs.budget, interests: prefs.interests.join(','), start_date: prefs.start_date })
      const response = await api(`/api/recommendations?${q}`); setRecommendations(await response.json())
    } catch (e) { setError(e.message) } finally { setLoading('') }
  }, [prefs, api])

  const searchPhotos = useCallback(async (query) => {
    if (!query) return
    try { const response = await api(`/api/images?query=${encodeURIComponent(query)}`); setPhotos((await response.json()).results || []) } catch { setPhotos([]) }
  }, [api])

  const generate = async (destination = prefs.destination) => {
    if (!session) {
      setAuthMode('signin')
      setAuthOpen(true)
      setAuthMessage('Sign in or create an account before generating an itinerary.')
      return
    }
    if (!destination.trim()) { setError('Choose a destination or pick one of the recommendations first.'); return }
    setLoading('generate'); setError(''); setNotice('')
    try {
      const response = await api('/api/itinerary/generate', { method: 'POST', body: JSON.stringify({ preferences: { ...prefs, destination, currency_code: destinationCurrency(destination) } }) })
      const data = await response.json(); setPlan({ ...data, accommodations: normalizeStays(data.accommodations, destination, prefs.budget), id: null }); setPrefs((p) => ({ ...p, destination })); setTab('Itinerary'); setSelectedDay(0); setNotice(data.ai_warning || (data.source !== 'demo' ? `Your ${data.source} itinerary is ready.` : 'Your demo itinerary is ready. AI generation was unavailable, so we used the built-in sample planner.'))
      searchPhotos(destination)
    } catch (e) { setError(e.message) } finally { setLoading('') }
  }

  const chooseCity = (city) => { setPrefs((p) => ({ ...p, destination: city })); generate(city) }

  const patchPlan = async (url, payload, pendingName) => {
    if (!plan) return
    if (!session) {
      setAuthMode('signin')
      setAuthOpen(true)
      setAuthMessage('Sign in before changing an itinerary.')
      return
    }
    setLoading(pendingName); setError(''); setNotice('')
    try {
      const response = await api(url, { method: 'POST', body: JSON.stringify({ ...payload, days: plan.days, preferences: plan.preferences }) })
      const data = await response.json();
      const next = { ...plan, days: data.days }
      setPlan(next)
      let syncWarning = ''
      if (plan.id) {
        try { await api(`/api/trips/${plan.id}`, { method: 'PATCH', body: JSON.stringify({ itinerary: next.days, preferences: next.preferences }) }) }
        catch (e) { syncWarning = ` The change is shown here but could not sync to your saved trip: ${e.message}` }
      }
      setNotice(`${data.ai_warning || 'Updated your plan. The rest stays in place.'}${syncWarning}`)
    } catch (e) { setError(e.message) } finally { setLoading('') }
  }

  const saveTrip = async () => {
    if (!session) { setAuthOpen(true); setAuthMessage('Sign in to save your trip across devices.'); return }
    if (!plan) return
    setLoading('save'); setError('')
    try {
      const payload = { name: `${plan.preferences.destination} getaway`, destination: plan.preferences.destination, start_date: plan.preferences.start_date, duration: plan.days.length, preferences: plan.preferences, itinerary: plan.days, accommodations: plan.accommodations || [], transportation: plan.transportation || {} }
      const response = plan.id ? await api(`/api/trips/${plan.id}`, { method: 'PATCH', body: JSON.stringify({ preferences: payload.preferences, itinerary: payload.itinerary, accommodations: payload.accommodations, transportation: payload.transportation }) }) : await api('/api/trips', { method: 'POST', body: JSON.stringify(payload) })
      const item = await response.json(); setPlan((p) => ({ ...p, id: item.id, share_code: item.share_code })); setSaved((items) => [item, ...items.filter((x) => x.id !== item.id)]); setNotice('Trip saved and ready to share with your group.')
    } catch (e) { setError(e.message) } finally { setLoading('') }
  }

  const loadTrip = (trip) => { const loaded = normalizeLegacyPlan({ id: trip.id, share_code: trip.share_code, preferences: trip.preferences, days: trip.itinerary, accommodations: trip.accommodations || [], transportation: trip.transportation || {} }, trip.destination); setPlan({ ...loaded, accommodations: normalizeStays(loaded.accommodations, trip.destination, loaded.preferences?.budget) }); setPrefs((p) => ({ ...p, ...loaded.preferences })); setSelectedDay(0); setTab('Itinerary'); setShowSaved(false); searchPhotos(trip.destination) }
  const joinTrip = async (value = joinCode) => {
    if (!session) { setAuthOpen(true); setAuthMessage('Sign in first to join a shared trip.'); return }
    try { await api('/api/trips/join', { method: 'POST', body: JSON.stringify({ share_code: value.trim() }) }); setJoinCode(''); await loadTrips(); setNotice('You joined the shared trip.'); }
    catch (e) { setError(e.message) }
  }
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('join')
    if (!session || !code) return
    window.history.replaceState({}, '', window.location.pathname)
    setShowSaved(true)
    joinTrip(code)
  }, [session])
  const shareTrip = async (trip) => {
    if (!trip.id) { setError('Save the trip before inviting collaborators.'); return }
    try {
      let code = trip.share_code
      if (!code) { const response = await api(`/api/trips/${trip.id}/share`, { method: 'POST' }); code = (await response.json()).share_code; setSaved((items) => items.map((x) => x.id === trip.id ? { ...x, share_code: code } : x)) }
      await navigator.clipboard.writeText(`${window.location.origin}/?join=${encodeURIComponent(code)}`); setNotice('Private invite link copied. Share it with signed-in collaborators.')
    } catch (e) { setError(`Could not copy invite link: ${e.message}`) }
  }
  const deleteTrip = async (id) => {
    try { await api(`/api/trips/${id}`, { method: 'DELETE' }); setSaved((items) => items.filter((x) => x.id !== id)); setNotice('Trip removed.') } catch (e) { setError(e.message) }
  }
  const exportPdf = async () => {
    if (!session || !plan) { setAuthOpen(true); setAuthMessage('Sign in to export your PDF guide.'); return }
    setLoading('pdf'); setError('')
    try {
      const response = await api('/api/itinerary/pdf', { method: 'POST', body: JSON.stringify({ preferences: plan.preferences, days: plan.days, accommodations: plan.accommodations || [], transportation: plan.transportation || {}, currency_code: destinationCurrency(plan.preferences.destination), currency_rate: exchangeRates[destinationCurrency(plan.preferences.destination)] || FALLBACK_USD_RATES[destinationCurrency(plan.preferences.destination)] }) })
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${plan.preferences.destination.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-itinerary.pdf`; a.click(); URL.revokeObjectURL(url)
    } catch (e) { setError(e.message) } finally { setLoading('') }
  }
  const submitAuth = async (e) => {
    e.preventDefault(); if (!supabase) { setAuthMessage('Add the Supabase URL and anon key to frontend/.env to enable accounts.'); return }
    setLoading('auth'); setAuthMessage('')
    try {
      const { error: authError } = authMode === 'signup' ? await supabase.auth.signUp({ email, password }) : await supabase.auth.signInWithPassword({ email, password })
      if (authError) throw authError
      setAuthMessage(authMode === 'signup' ? 'Check your email to confirm your account.' : 'Signed in successfully.'); if (authMode === 'signin') setAuthOpen(false)
    } catch (e2) { setAuthMessage(e2.message) } finally { setLoading('') }
  }
  const signOut = async () => { await supabase?.auth.signOut(); setSession(null); setSaved([]); setShowSaved(false) }

  useEffect(() => {
    if (!supabase || !plan?.id || !session) return undefined
    const channel = supabase.channel(`trip-${plan.id}`).on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'trips', filter: `id=eq.${plan.id}` }, (event) => {
      const row = event.new
      setPlan((current) => { if (current?.id !== row.id) return current; const updated = normalizeLegacyPlan({ ...current, preferences: row.preferences, days: row.itinerary, accommodations: row.accommodations || [], transportation: row.transportation || {} }, row.destination); return { ...updated, accommodations: normalizeStays(updated.accommodations, row.destination, updated.preferences?.budget) } })
      setNotice('A collaborator updated this shared trip.')
    }).subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [plan?.id, session])

  const total = useMemo(() => (plan?.days || []).flatMap((d) => d.items || []).reduce((sum, item) => sum + Number(item.cost_usd || 0), 0), [plan])
  const nights = Math.max(1, (plan?.days?.length || 1) - 1)
  const lodgingPerPerson = plan?.accommodations?.length ? Number(plan.accommodations[Math.min(plan.preferences.budget === 'Budget' ? 0 : plan.preferences.budget === 'Luxury' ? 2 : 1, plan.accommodations.length - 1)].estimated_nightly_usd || 0) * nights : 0
  const transportPerPerson = plan ? Array.from({ length: plan.days.length }, (_, i) => Number(plan.transportation?.daily_transfers?.[i]?.estimated_transit_usd_per_person ?? 8)).reduce((sum, amount) => sum + amount, 0) : 0
  const currentDay = plan?.days?.[selectedDay]
  const stayRecommendations = useMemo(() => {
    const stays = plan?.accommodations || []
    if (!stays.length) return []
    const budget = plan?.preferences?.budget || 'Moderate'
    const tier = { Budget: ['budget', 0], Moderate: ['moderate', 1], Luxury: [['premium', 'luxury'], 2] }[budget] || ['moderate', 1]
    const aliases = Array.isArray(tier[0]) ? tier[0] : [tier[0]]
    const matched = stays.find((stay) => aliases.some((label) => String(stay.style || '').toLowerCase().includes(label)))
    const selected = matched || stays[Math.min(tier.at(-1), stays.length - 1)]
    const destination = plan?.preferences?.destination || ''
    const city = destination.split(',')[0].trim()
    const areas = Object.entries(STAY_AREAS).find(([name]) => city.toLowerCase().includes(name.toLowerCase()))?.[1] || [`Central ${city}`, `Near public transit in ${city}`, `A quieter area near ${city} centre`]
    const styles = {
      Budget: ['Guesthouse', 'Local homestay', 'Budget hotel'],
      Moderate: ['Well-rated local hotel', 'Boutique stay', 'Serviced apartment'],
      Luxury: ['Heritage hotel', 'Boutique resort', 'Luxury hotel'],
    }[budget] || ['Well-rated local hotel', 'Boutique stay', 'Serviced apartment']
    const reasons = {
      Budget: ['A simple, lower-cost base for exploring nearby areas.', 'A homestay option for travelers who prefer a local feel.', 'A practical hotel option with convenient access around town.'],
      Moderate: ['A comfortable base with a balance of convenience and price.', 'A smaller stay with a more distinctive local character.', 'Extra room and flexibility for a longer visit.'],
      Luxury: ['A high-comfort option with a sense of local history.', 'A polished stay for a more relaxed trip.', 'A premium option with elevated comfort and service.'],
    }[budget] || []
    const price = Number(selected.estimated_nightly_usd) || 0
    return areas.map((area, index) => ({
      ...selected,
      style: styles[index],
      area,
      estimated_nightly_usd: Math.round(price * [0.9, 1, 1.12][index] * 100) / 100,
      why: `${reasons[index]} Compare current room rates, reviews, and cancellation terms.`,
    }))
  }, [plan?.accommodations, plan?.preferences?.budget, plan?.preferences?.destination])
  const scrollToPlanner = () => document.getElementById('planner')?.scrollIntoView({ behavior: 'smooth' })

  if (!authReady) return <div className="boot"><LoaderCircle className="spin" /> Getting your trip desk ready…</div>

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#top" aria-label="Personalized Travel Itinerary Planner home"><span className="brand-mark"><Compass size={21} /></span><span className="brand-full">Personalized Travel Itinerary Planner<small>YOUR TRAVEL STUDIO</small></span><span className="brand-short">Travel Planner<small>YOUR TRAVEL STUDIO</small></span></a>
      <nav className="desktop-nav"><button className={tab === 'Discover' ? 'nav-link active' : 'nav-link'} onClick={() => setTab('Discover')}>Discover</button><button className={tab === 'Itinerary' ? 'nav-link active' : 'nav-link'} onClick={() => setTab('Itinerary')}>My itinerary</button><button className={tab === 'Vibe' ? 'nav-link active' : 'nav-link'} onClick={() => setTab('Vibe')}>Make it yours</button></nav>
      <div className="top-actions"><button className="saved-trigger" onClick={() => setShowSaved(true)}><Heart size={17} /> <span>Saved trips</span>{saved.length > 0 && <b>{saved.length}</b>}</button>{session ? <button className="avatar" title={session.user.email} onClick={signOut}>{session.user.email?.[0]?.toUpperCase()}<LogOut size={13} /></button> : <button className="signin-button" onClick={() => setAuthOpen(true)}>Sign in <ArrowRight size={15} /></button>}</div>
    </header>

    {serviceConfig && (!serviceConfig.ai_configured || !serviceConfig.supabase_configured) && <div className="alert error service-config-alert"><X size={16} /><span>{[!serviceConfig.ai_configured && `${serviceConfig.ai_provider === 'groq' ? 'Groq' : 'Gemini'} API key missing: itineraries use demo plans. Add it to backend/.env and restart FastAPI.`, !serviceConfig.supabase_configured && 'Supabase is not configured: sign-in, saved trips, and collaboration are unavailable. Set the real project URL and anon key in backend/.env and frontend/.env.'].filter(Boolean).join(' ')}</span></div>}

    {tab === 'Discover' && <>
      <main id="top">
        <section className="hero-wrap">
          <div className="hero-backdrop" />
          <div className="hero-copy"><div className="eyebrow"><span /> THE ART OF GETTING AWAY</div><h1>Go where you<br /><em>feel most alive.</em></h1><p>A thoughtful little travel studio for the places you dream about and the days you’ll remember.</p><button className="primary-button hero-cta" onClick={scrollToPlanner}>Plan a journey <ArrowDown size={17} /></button><div className="hero-foot"><span><Sun size={16} /> Season-led ideas</span><i /> <span><MapPin size={16} /> Neighborhood-first routes</span></div></div>
          <div className="hero-image" role="img" aria-label="Mountain lake travel landscape"><div className="hero-image-caption"><span>FIELD NOTES / 01</span><strong>The world, at your pace.</strong></div><span className="image-credit">Photography via Unsplash</span></div>
          <div className="hero-index">01 <span>—</span> 04</div>
        </section>

        <section className="planner-section" id="planner">
          <div className="section-heading"><div><div className="eyebrow">A good trip starts with a feeling</div><h2>Tell us what moves you.</h2></div><div className="section-note">A few thoughtful details help us<br />find your kind of somewhere.</div></div>
          <div className="planner-card">
            <div className="field-grid">
              <label className="field wide"><span><MapPin size={15} /> WHERE TO?</span><input value={prefs.destination} onChange={(e) => setPrefs({ ...prefs, destination: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && generate()} placeholder="A city, a coast, or leave it open" /></label>
              <label className="field"><span><CalendarDays size={15} /> FIRST DAY</span><input type="date" min={new Date().toISOString().slice(0, 10)} value={prefs.start_date} onChange={(e) => setPrefs({ ...prefs, start_date: e.target.value })} /></label>
              <label className="field"><span><Sun size={15} /> HOW LONG?</span><select value={prefs.duration} onChange={(e) => setPrefs({ ...prefs, duration: Number(e.target.value) })}>{Array.from({ length: 21 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d} {d === 1 ? 'day' : 'days'}</option>)}</select><ChevronDown className="select-chevron" size={14} /></label>
            </div>
            <div className="planner-divider" />
            <div className="preference-row"><div className="pref-block"><span className="field-label">THE MOOD</span><div className="choice-row">{VIBES.map((v) => <button key={v} className={`choice ${prefs.vibe === v ? 'selected' : ''}`} onClick={() => setPrefs({ ...prefs, vibe: v })}>{v === 'Beach' ? <Sun size={14} /> : v === 'Mountains' ? <Mountain size={14} /> : v === 'Cultural' ? <Sparkles size={14} /> : <Compass size={14} />}{v}</button>)}</div></div><div className="pref-block"><span className="field-label">THE COMPANY</span><div className="select-wrap"><select value={prefs.party} onChange={(e) => { const party = e.target.value; setPrefs({ ...prefs, party, group_size: party === 'Solo' ? 1 : party === 'Couple' ? 2 : party === 'Family' ? 4 : 4 }) }}>{['Solo', 'Couple', 'Family', 'Friends'].map((x) => <option key={x}>{x}</option>)}</select><ChevronDown size={14} /></div></div><div className="pref-block"><span className="field-label">GROUP SIZE</span><div className="select-wrap"><select value={prefs.group_size} onChange={(e) => setPrefs({ ...prefs, group_size: Number(e.target.value) })}>{Array.from({ length: 12 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n} {n === 1 ? 'traveler' : 'travelers'}</option>)}</select><ChevronDown size={14} /></div></div><div className="pref-block"><span className="field-label">YOUR PACE</span><div className="select-wrap"><select value={prefs.pace} onChange={(e) => setPrefs({ ...prefs, pace: e.target.value })}>{['Relaxed', 'Moderate', 'Fast-Paced'].map((x) => <option key={x}>{x}</option>)}</select><ChevronDown size={14} /></div></div><div className="pref-block"><span className="field-label">YOUR BUDGET</span><div className="select-wrap"><select value={prefs.budget} onChange={(e) => setPrefs({ ...prefs, budget: e.target.value })}>{['Budget', 'Moderate', 'Luxury'].map((x) => <option key={x} value={x}>{BUDGET_LABELS[x]}</option>)}</select><ChevronDown size={14} /></div></div></div>
            <div className="interest-row"><span className="field-label">I'M INTO</span>{INTERESTS.map((x) => <button key={x} className={`interest-chip ${prefs.interests.includes(x) ? 'on' : ''}`} onClick={() => setPrefs({ ...prefs, interests: prefs.interests.includes(x) ? prefs.interests.filter((i) => i !== x) : [...prefs.interests, x] })}>{prefs.interests.includes(x) && <Check size={13} />}{x}</button>)}<button className="interest-chip add-interest" title="Add an interest" onClick={() => setPrefs({ ...prefs, interests: prefs.interests.includes('Architecture') ? prefs.interests : [...prefs.interests, 'Architecture'] })}><Plus size={15} /> Add your own</button></div>
            <div className="planner-bottom"><span className="privacy-note"><span className="tiny-dot" /> Sign in required to create itineraries.</span><button className="primary-button" onClick={() => generate()} disabled={!!loading}>{loading === 'generate' ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />} {session ? 'Create my itinerary' : 'Sign in to plan'} <ArrowRight size={16} /></button></div>
          </div>
          <div className="discover-link"><button onClick={getRecommendations}><Sparkles size={16} /> Not sure where? Let the season decide <ArrowRight size={15} /></button></div>
          {recommendations.length > 0 && <div className="recommendation-grid">{recommendations.map((r) => <article className="destination-card" key={r.city}><div className="destination-photo" style={{ backgroundImage: `linear-gradient(0deg,#15332dcc,transparent 70%),url(https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=900&q=80)` }}><span className="photo-label">{r.season}</span><h3>{r.city}</h3></div><div className="destination-copy"><p>{r.description}</p><div className="tag-row">{r.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</div><p className="highlights">{r.highlights}</p><button className="text-arrow" onClick={() => chooseCity(r.city)}>Plan this escape <ArrowRight size={15} /></button></div></article>)}</div>}
        </section>
        <section className="manifesto"><div className="manifesto-mark">“</div><div><div className="eyebrow">A NOTE FROM YOUR TRAVEL PLANNER</div><p>“The best itinerary has just enough of a plan to help you get wonderfully lost.”</p><span>Thoughtful routes. Room to wander.</span></div><div className="manifesto-aside"><span>DESIGNED FOR THE<br />WAY YOU TRAVEL.</span><ArrowDown size={18} /></div></section>
      </main>
    </>}

    {tab === 'Itinerary' && <main className="workspace">
      <div className="workspace-head">
        <div><div className="eyebrow">YOUR DAYS, BEAUTIFULLY LAID OUT</div><h1>{plan ? plan.preferences.destination : 'Your travel journal'}</h1><p>{plan ? `${plan.days.length} days · ${plan.preferences.start_date} · ${plan.preferences.group_size || 1} travelers · ${plan.preferences.pace} pace` : 'Make a plan and your itinerary will live here.'}</p></div>
        <div className="workspace-actions">{plan && <><button className="soft-button" onClick={saveTrip} disabled={!!loading}><Heart size={16} /> {plan.id ? 'Save changes' : 'Save trip'}</button>{plan.id && <button className="soft-button" onClick={() => shareTrip({ ...plan, share_code: plan.share_code || saved.find((x) => x.id === plan.id)?.share_code })}><Plus size={16} /> Invite group</button>}<button className="primary-button" onClick={exportPdf} disabled={!!loading}>{loading === 'pdf' ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />} Offline guide</button></>}</div>
      </div>
      {!plan ? <div className="empty-state"><div className="empty-illustration"><Compass size={46} /></div><h2>Your next chapter is unwritten.</h2><p>Head to Discover and tell us where the feeling takes you.</p><button className="primary-button" onClick={() => setTab('Discover')}>Start planning <ArrowRight size={16} /></button></div> : <>
        <div className="trip-summary"><div className="summary-photo" style={{ backgroundImage: photos[0] ? `url(${photos[0].url})` : undefined }}><span>{plan.preferences.vibe} escape</span></div><div className="summary-content"><div className="summary-stats"><div><span>TRIP LENGTH</span><b>{plan.days.length} days</b></div><div><span>EST. ACTIVITIES · PER PERSON</span><b>{destinationMoney(total, plan.preferences.destination, exchangeRates)}</b></div><div><span>EST. TRIP TOTAL · GROUP</span><b>{destinationMoney((total + lodgingPerPerson + transportPerPerson) * (plan.preferences.group_size || 1), plan.preferences.destination, exchangeRates)} · {plan.preferences.group_size || 1} people</b></div><div><span>TRAVEL STYLE</span><b>{BUDGET_LABELS[plan.preferences.budget] || plan.preferences.budget} · {plan.preferences.pace}</b></div></div><div className="cost-note">Activity totals are per person; lodging and transport are estimated separately. Costs are shown in the destination currency using the latest available daily reference rate.</div></div></div>
        <div className="planner-extras">
          <section className="extras-panel"><div className="eyebrow">A GOOD PLACE TO LAND</div><h2>Stay options · {BUDGET_LABELS[plan.preferences.budget] || plan.preferences.budget}</h2><p className="extras-intro">Three neighborhood and stay-style ideas for your selected price tier. These are suggestions, not live hotel listings.</p><div className="stay-grid">{stayRecommendations.map((stay, i) => { const searchArea = stay.area.replace(/\s*&\s*/g, ', '); const query = `hotels in ${searchArea}, ${plan.preferences.destination}`; return <article className="stay-card" key={`${stay.style}-${i}`}><span className="stay-price">≈ {destinationMoney(stay.estimated_nightly_usd, plan.preferences.destination, exchangeRates)} <small>/ night / person</small></span><h3>{stay.style}</h3><b>{stay.area}</b><p>{stay.why}</p><a className="text-arrow" href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`} target="_blank" rel="noreferrer">Browse current stays <ArrowRight size={14} /></a></article> })}</div></section>
          <section className="extras-panel transport-panel"><div className="eyebrow">GETTING AROUND</div><h2>Transport & route notes</h2><p>{plan.transportation?.route_summary || plan.transportation?.route_method}</p><div className="transport-grid"><div><b>Arrival</b><p>{plan.transportation?.arrival}</p></div><div><b>Local transport</b><p>{plan.transportation?.local}</p></div></div><p className="route-disclaimer">These are planning suggestions, not live directions or traffic data. Verify routes, fares, accessibility, and schedules with current local sources.</p></section>
        </div>
        <div className="itinerary-layout"><div className="day-rail">{plan.days.map((d, i) => <button key={i} className={`day-tab ${selectedDay === i ? 'current' : ''}`} onClick={() => setSelectedDay(i)}><span>DAY {String(i + 1).padStart(2, '0')}</span><b>{d.area || plan.preferences.destination}</b><small>{d.items?.length || 0} moments</small></button>)}</div>
          <section className="day-detail"><div className="day-title"><div><span className="eyebrow">DAY {String(selectedDay + 1).padStart(2, '0')} · NEIGHBORHOOD ROUTE</span><h2>{currentDay?.area || plan.preferences.destination}</h2><p>{currentDay?.route_note || 'Stops are grouped to reduce backtracking.'}</p></div><div className="day-tools"><a className="soft-button map-route" href={mapsRouteUrl(currentDay, plan.preferences.destination)} target="_blank" rel="noreferrer"><MapPin size={14} /> Open day route in Maps</a><button className="icon-button" aria-label="Regenerate this day" title="Regenerate day" onClick={() => patchPlan('/api/itinerary/regenerate-day', { day_index: selectedDay, request: 'Fresh ideas' }, 'day')}>{loading === 'day' ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}</button></div></div>
            <div className="timeline">{currentDay?.items?.map((item, i) => { const cumulative = plan.days.slice(0, selectedDay).flatMap((d) => d.items || []).concat((currentDay?.items || []).slice(0, i + 1)).reduce((sum, entry) => sum + Number(entry.cost_usd || 0), 0); return <article className="timeline-item" key={`${selectedDay}-${i}`}><div className="timeline-time"><span>{TIMES[i]}</span><i /></div><div className="timeline-card"><div className="timeline-category">{i === 1 ? <Utensils size={14} /> : i === 2 ? <Sun size={14} /> : <MapPin size={14} />}{item.slot || SLOTS[i]}</div><div className="timeline-title-row"><h3>{item.title}</h3><span className="cost">{destinationMoney(item.cost_usd || 0, plan.preferences.destination, exchangeRates)} <small>/ person</small></span></div><p>{item.description}</p>{item.transit_to_next && <p className="transit-note">↳ Next: {item.transit_to_next}</p>}<div className="running-total">Running activity estimate: {destinationMoney(cumulative, plan.preferences.destination, exchangeRates)} / person · {destinationMoney(cumulative * (plan.preferences.group_size || 1), plan.preferences.destination, exchangeRates)} group total</div><button className="swap-link" onClick={() => { setSelectedSlot(i); setTab('Vibe') }}><RefreshCw size={13} /> Swap this moment</button></div></article> })}</div>
          </section>
        </div>
      </>}
    </main>}
      {error && <div className="alert error"><X size={16} />{error}<button onClick={() => setError('')}><X size={15} /></button></div>}{notice && <div className="alert success"><Check size={16} />{notice}<button onClick={() => setNotice('')}><X size={15} /></button></div>}

    {tab === 'Vibe' && <main className="workspace vibe-workspace"><div className="workspace-head"><div><div className="eyebrow">THE PLAN IS YOURS TO PLAY WITH</div><h1>Make it feel like you.</h1><p>Change one moment or reimagine a whole day. Your other plans stay put.</p></div></div>{!plan ? <div className="empty-state"><h2>Start with a journey.</h2><p>Build your itinerary first, then tune it to your mood.</p><button className="primary-button" onClick={() => setTab('Discover')}>Find a destination <ArrowRight size={16} /></button></div> : <div className="customize-grid"><div className="customize-aside"><div className="customize-kicker"><WandSparkles size={19} /> LIVE ITINERARY EDITOR</div><h2>A little tweak can change everything.</h2><p>Ask for a different flavor of the day. The rest of your trip remains exactly as you planned it.</p><div className="vibe-tip"><Sparkles size={17} /><span><b>Try a prompt</b>“Swap this moment for a local outdoor market” or “Find a vegetarian lunch spot.”</span></div></div><div className="edit-panel"><div className="edit-field"><label>WHICH DAY?</label><select value={selectedDay} onChange={(e) => setSelectedDay(Number(e.target.value))}>{plan.days.map((d, i) => <option key={i} value={i}>Day {i + 1} · {d.area}</option>)}</select></div><div className="edit-field"><label>WHICH MOMENT?</label><select value={selectedSlot} onChange={(e) => setSelectedSlot(Number(e.target.value))}>{(plan.days[selectedDay]?.items || []).map((x, i) => <option key={i} value={i}>{x.slot || SLOTS[i]} · {x.title}</option>)}</select></div><label className="edit-field"><span>WHAT ARE YOU IN THE MOOD FOR?</span><textarea value={swapRequest} onChange={(e) => setSwapRequest(e.target.value)} placeholder="e.g. Find a vegetarian lunch spot with a garden terrace…" rows={4} /></label><div className="prompt-chips"><button onClick={() => setSwapRequest(`Replace ${plan.days[selectedDay]?.items?.[selectedSlot]?.title || 'this activity'} with a nearby outdoor market`)}>Outdoor market</button><button onClick={() => setSwapRequest('Find a vegetarian lunch spot')}>Vegetarian lunch</button><button onClick={() => setSwapRequest('Add a relaxed local experience')}>Slow it down</button></div><div className="edit-actions"><button className="soft-button" onClick={() => patchPlan('/api/itinerary/regenerate-day', { day_index: selectedDay, request: swapRequest || 'Fresh ideas' }, 'day')} disabled={!!loading}>{loading === 'day' ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} Reimagine whole day</button><button className="primary-button" onClick={() => patchPlan('/api/itinerary/swap', { day_index: selectedDay, slot_index: selectedSlot, request: swapRequest || 'Suggest a fresh local option' }, 'swap')} disabled={!!loading}>{loading === 'swap' ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} Swap this moment</button></div></div></div>}</main>}

    <footer className="footer"><a className="brand footer-brand" href="#top"><span className="brand-mark"><Compass size={18} /></span><span className="brand-full">Personalized Travel Itinerary Planner<small>YOUR TRAVEL STUDIO</small></span><span className="brand-short">Travel Planner<small>YOUR TRAVEL STUDIO</small></span></a><span>Thoughtfully planned. Happily wandered.</span><span>© 2026 Personalized Travel Itinerary Planner</span></footer>

    {error && tab !== 'Itinerary' && <div className="toast error-toast"><X size={16} />{error}<button onClick={() => setError('')}><X size={14} /></button></div>}
    {notice && tab !== 'Itinerary' && <div className="toast success-toast"><Check size={16} />{notice}<button onClick={() => setNotice('')}><X size={14} /></button></div>}

    {showSaved && <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && setShowSaved(false)}><aside className="drawer"><div className="drawer-head"><div><div className="eyebrow">YOUR SHARED TRAVEL JOURNAL</div><h2>Saved journeys</h2></div><button className="icon-button" onClick={() => setShowSaved(false)}><X size={19} /></button></div>{!session ? <div className="drawer-empty"><Heart size={28} /><p>Sign in to keep your trips safe and close.</p><button className="primary-button" onClick={() => { setShowSaved(false); setAuthOpen(true) }}>Sign in <ArrowRight size={16} /></button></div> : <><div className="join-trip"><label htmlFor="join-code">JOIN YOUR GROUP'S TRIP</label><div><input id="join-code" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Paste invite code" /><button className="primary-button" onClick={() => joinTrip()} disabled={!joinCode.trim()}>Join</button></div><small>Collaborators need an account. Open an invite link after signing in, or paste its code here.</small></div>{saved.length === 0 ? <div className="drawer-empty compact"><Compass size={28} /><p>No trips saved yet. Create one, then invite your travel group.</p><button className="text-arrow" onClick={() => { setShowSaved(false); setTab('Discover') }}>Plan your first trip <ArrowRight size={15} /></button></div> : <div className="saved-list">{saved.map((trip) => <article className="saved-card" key={trip.id}><div className="saved-card-top"><span>{trip.duration} DAYS · {trip.start_date}{trip.user_id !== session.user.id ? ' · SHARED' : ''}</span>{trip.user_id === session.user.id && <button className="icon-button tiny" onClick={() => deleteTrip(trip.id)} title="Delete trip"><Trash2 size={15} /></button>}</div><h3>{trip.destination}</h3><p>{trip.name} · {trip.preferences?.group_size || 1} travelers</p><div className="saved-card-actions"><button className="text-arrow" onClick={() => loadTrip(trip)}>Open this trip <ArrowRight size={15} /></button>{trip.share_code && <button className="share-code" onClick={() => shareTrip(trip)}>Copy invite link</button>}</div></article>)}</div>}</>}</aside></div>}

    {authOpen && <div className="overlay modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && setAuthOpen(false)}><section className="auth-modal"><button className="modal-close icon-button" onClick={() => setAuthOpen(false)}><X size={18} /></button><div className="auth-icon"><Compass size={24} /></div><div className="eyebrow">YOUR TRAVEL STUDIO</div><h2>{authMode === 'signin' ? 'Welcome back.' : 'Come on in.'}</h2><p>Keep your favorite plans tucked safely away.</p><form onSubmit={submitAuth}><label>Email address<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></label><label>Password<input type="password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" /></label><button className="primary-button auth-submit" disabled={loading === 'auth'}>{loading === 'auth' ? <LoaderCircle className="spin" size={16} /> : <LogIn size={16} />}{authMode === 'signin' ? 'Sign in' : 'Create account'} <ArrowRight size={16} /></button></form>{authMessage && <p className="auth-message">{authMessage}</p>}<p className="auth-switch">{authMode === 'signin' ? 'New around here?' : 'Already have an account?'} <button onClick={() => { setAuthMode(authMode === 'signin' ? 'signup' : 'signin'); setAuthMessage('') }}>{authMode === 'signin' ? 'Create an account' : 'Sign in'}</button></p>{!supabase && <p className="auth-config">Supabase isn’t configured yet. See the setup guide to enable accounts.</p>}</section></div>}
  </div>
}

export default App
