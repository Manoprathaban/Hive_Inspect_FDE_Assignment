import { memo } from 'react'
import type { Section } from '../types'
import { ItemView } from './ItemView'
import { InlineTextEditor } from './InlineTextEditor'

interface SectionViewProps {
  section: Section
  onRenameSection: (sectionId: string, name: string) => Promise<void>
  onRenameItem: (itemId: string, name: string) => Promise<void>
  onEditContent: (commentId: string, content: string) => Promise<void>
}

/** One ordered section with its items nested. */
export const SectionView = memo(function SectionView({
  section,
  onRenameSection,
  onRenameItem,
  onEditContent,
}: SectionViewProps) {
  return (
    <section className="section-row">
      <h3 className="section-heading">
        <InlineTextEditor
          value={section.name}
          onSave={(name) => onRenameSection(section.id, name)}
          mode="name"
          label={`section "${section.name}"`}
        />
        <span className="section-count">{section.items.length} items</span>
      </h3>
      {section.items.length > 0 && (
        <ul className="item-list">
          {section.items.map((item) => (
            <ItemView key={item.id} item={item} onRenameItem={onRenameItem} onEditContent={onEditContent} />
          ))}
        </ul>
      )}
    </section>
  )
})