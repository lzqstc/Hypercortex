import { useRef } from 'react'
import type { ChangeEvent } from 'react'

export const useFilePicker = (
  onFiles: (files: File[]) => void,
  options?: { multiple?: boolean; accept?: string },
) => {
  const inputRef = useRef<HTMLInputElement>(null)
  const multiple = options?.multiple ?? true

  const open = () => inputRef.current?.click()

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length) onFiles(files)
    event.target.value = ''
  }

  const input = (
    <input
      ref={inputRef}
      type="file"
      hidden
      multiple={multiple}
      accept={options?.accept}
      onChange={handleChange}
    />
  )

  return { open, input }
}
