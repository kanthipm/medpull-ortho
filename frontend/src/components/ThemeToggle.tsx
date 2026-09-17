import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../lib/theme'

/** App-bar icon button: an ink glyph (the glass bar carries ink only, R2),
 *  a --soft capsule on hover, the --focus ring with its --panel halo. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const dark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
      className="btn-icon"
    >
      {dark ? <Sun aria-hidden size={20} /> : <Moon aria-hidden size={20} />}
    </button>
  )
}
