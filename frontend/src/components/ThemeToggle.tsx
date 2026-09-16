import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../lib/theme'

/** App-bar icon button — white on the primary bar. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const dark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
      className="grid h-10 w-10 cursor-pointer place-items-center rounded-btn text-white transition-colors duration-150 hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
    >
      {dark ? <Sun size={20} /> : <Moon size={20} />}
    </button>
  )
}
