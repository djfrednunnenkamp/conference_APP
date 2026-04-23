import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

const AuthContext = createContext({})

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  async function fetchProfile(userId) {
    const { data } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', userId)
      .single()
    setProfile(data)

    // If profile is 'parent' (default role), check if there's a pending teacher invite.
    // This runs finalize-teacher as a fallback in case ResetPasswordPage's call failed.
    if (data?.role === 'parent' && data?.email) {
      const { data: invites } = await supabase
        .from('teacher_invites')
        .select('id')
        .eq('email', data.email)
        .limit(1)

      if (invites?.length > 0) {
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (token) {
          fetch(
            `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/finalize-teacher`,
            {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${token}`,
                'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
              },
            }
          ).then(async (res) => {
            if (res.ok) {
              // Reload profile now that teacher setup is complete
              const { data: updated } = await supabase
                .from('profiles')
                .select('*')
                .eq('id', userId)
                .single()
              setProfile(updated)
            }
          }).catch(() => {})
        }
      }
    }
  }

  useEffect(() => {
    supabase.auth.getSession()
      .then(({ data: { session } }) => {
        setUser(session?.user ?? null)
        if (session?.user) fetchProfile(session.user.id)
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      if (session?.user) fetchProfile(session.user.id)
      else setProfile(null)
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  async function signIn(email, password) {
    return supabase.auth.signInWithPassword({ email, password })
  }

  async function signUp(email, password, meta) {
    return supabase.auth.signUp({ email, password, options: { data: meta } })
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  async function resetPassword(email) {
    return supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
  }

  const isAdmin   = profile?.role === 'admin'
  const isTeacher = profile?.role === 'teacher'
  const isParent  = profile?.role === 'parent'

  return (
    <AuthContext.Provider value={{
      user, profile, loading,
      isAdmin, isTeacher, isParent,
      signIn, signUp, signOut, resetPassword,
      refreshProfile: () => user && fetchProfile(user.id),
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
