import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../lib/theme'

/** Header control — flips the calibrated instrument between paper and night. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const dark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
      className="grid h-8 w-8 cursor-pointer place-items-center rounded-btn border border-line bg-panel text-muted transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
    >
      {dark ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}
