/* The phone draws SF Symbols; the web draws the nearest Lucide glyph for
   each one, under the SF name the screens already use, so a screen ported
   from Swift keeps its `symbol: "figure.walk"` lines word for word. */

import type { LucideIcon, LucideProps } from 'lucide-react'
import {
  Activity, Armchair, ArrowRight, ArrowUp, AudioLines, BadgeCheck, Bandage, BedDouble,
  BriefcaseMedical, Building2, Calendar, Camera, ChartLine, Check, ChevronDown, ChevronLeft,
  ChevronRight, CircleArrowRight, CircleArrowUp, CircleCheck, CircleMinus, CircleX, Compass,
  Droplet, Dumbbell, ExternalLink, Eye, EyeOff, File, FileText, Flame, Footprints, Gauge,
  GitBranch, Heart, HeartPulse, IdCard, Image, ImageOff, Images, Link, ListChecks, Mic,
  MessageCircle, MessageSquareText, MessagesSquare, Moon, Pause, Pencil, PersonStanding, Pill,
  Play, Plus, RefreshCw, Repeat, RotateCcw, Ruler, Search, Sparkles, Square, Stethoscope,
  Sun, Sunrise, Thermometer, Timer, TrendingUp, TriangleAlert, TriangleRight, Users, Video,
  VideoOff, Watch, Weight, Wind, X, Smartphone, Lock, Settings, Hourglass, Circle,
} from 'lucide-react'

const map: Record<string, LucideIcon> = {
  'sun.max.fill': Sun,
  'chart.line.uptrend.xyaxis': TrendingUp,
  'figure.walk.motion': Footprints,
  'figure.walk': Footprints,
  'figure.walk.arrival': Footprints,
  'figure.stand': PersonStanding,
  'figure.run': Activity,
  'figure.strengthtraining.functional': Dumbbell,
  'bubble.left.and.bubble.right.fill': MessagesSquare,
  'text.bubble.fill': MessageSquareText,
  'message.fill': MessageCircle,
  'pills.fill': Pill,
  'bandage.fill': Bandage,
  'bed.double.fill': BedDouble,
  checklist: ListChecks,
  checkmark: Check,
  'checkmark.circle.fill': CircleCheck,
  'checkmark.circle': CircleCheck,
  circle: Circle,
  'checkmark.seal.fill': BadgeCheck,
  'minus.circle': CircleMinus,
  'chevron.right': ChevronRight,
  'chevron.down': ChevronDown,
  'chevron.left': ChevronLeft,
  'heart.fill': Heart,
  applewatch: Watch,
  link: Link,
  'arrow.triangle.2.circlepath': RefreshCw,
  'play.fill': Play,
  'stop.fill': Square,
  'arrow.counterclockwise': RotateCcw,
  'arrow.up.circle.fill': CircleArrowUp,
  'arrow.up': ArrowUp,
  'arrow.right': ArrowRight,
  'arrow.right.circle.fill': CircleArrowRight,
  'arrow.up.forward.app': ExternalLink,
  plus: Plus,
  'mic.fill': Mic,
  xmark: X,
  'xmark.circle.fill': CircleX,
  camera: Camera,
  'photo.on.rectangle': Images,
  waveform: AudioLines,
  doc: File,
  'doc.richtext': FileText,
  'doc.text.fill': FileText,
  photo: Image,
  video: Video,
  'video.slash': VideoOff,
  'photo.badge.exclamationmark': ImageOff,
  'pause.fill': Pause,
  sparkles: Sparkles,
  pencil: Pencil,
  'exclamationmark.triangle.fill': TriangleAlert,
  magnifyingglass: Search,
  'building.2.fill': Building2,
  'building.2': Building2,
  'person.text.rectangle.fill': IdCard,
  'cross.case.fill': BriefcaseMedical,
  calendar: Calendar,
  'person.2.fill': Users,
  'gauge.with.dots.needle.67percent': Gauge,
  'gauge.with.needle': Gauge,
  speedometer: Gauge,
  'flame.fill': Flame,
  ruler: Ruler,
  metronome: Repeat,
  stairs: TrendingUp,
  timer: Timer,
  angle: TriangleRight,
  chair: Armchair,
  'moon.fill': Moon,
  'waveform.path.ecg': Activity,
  'sun.horizon.fill': Sunrise,
  'heart.text.square.fill': HeartPulse,
  'thermometer.medium': Thermometer,
  'arrow.triangle.branch': GitBranch,
  'scalemass.fill': Weight,
  'lungs.fill': Wind,
  'drop.fill': Droplet,
  stethoscope: Stethoscope,
  'chart.xyaxis.line': ChartLine,
  wind: Wind,
  'arrow.down.heart.fill': HeartPulse,
  eye: Eye,
  'eye.slash': EyeOff,
  compass: Compass,
  iphone: Smartphone,
  'lock.fill': Lock,
  gearshape: Settings,
  hourglass: Hourglass,
}

type Weight = 'regular' | 'medium' | 'semibold'

const strokeFor: Record<Weight, number> = { regular: 1.8, medium: 2.1, semibold: 2.5 }

export type SymbolProps = Omit<LucideProps, 'size'> & {
  /** The SF Symbol name the phone uses. */
  name: string
  size?: number
  weight?: Weight
}

/** An SF-named glyph: `<Sym name="figure.walk" size={16} />`. */
export function Sym({ name, size = 16, weight = 'medium', ...rest }: SymbolProps) {
  const Icon = map[name] ?? ChartLine
  return <Icon size={size} strokeWidth={strokeFor[weight]} aria-hidden="true" focusable="false" {...rest} />
}
