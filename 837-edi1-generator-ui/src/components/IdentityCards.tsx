/**
 * Section 04: subscriber and provider, shared across the whole batch.
 *
 * The fields are exactly the ones overrides.IDENTITY_FIELDS accepts; a field
 * the generator would refuse has no input here. Attending provider and tax id
 * appear only when the seed carries them (the 837P seed has no NM1*71*).
 */
import { autoTag, cardHeader, input, label } from '../styles/ui.js';
import type { Identity, IdentityGroup } from '../api/types.js';

interface Field {
  group: IdentityGroup;
  name: string;
  label: string;
  value: string;
}

interface Props {
  identity: Identity;
  editedGroups: Set<string>;
  onChange: (group: IdentityGroup, field: string, value: string) => void;
}

function Card(
  { name, groups, fields, editedGroups, onChange }: {
    name: string;
    groups: IdentityGroup[];
    fields: Field[];
    editedGroups: Set<string>;
    onChange: Props['onChange'];
  },
) {
  const untouched = groups.every((g) => !editedGroups.has(g));
  return (
    <div style={{
      border: '1px solid #dde1ea',
      borderRadius: 8,
      overflow: 'hidden',
      background: '#fff',
    }}
    >
      <div style={cardHeader}>
        <div style={{ fontSize: 14.5, fontWeight: 600 }}>{name}</div>
        {untouched && <div style={autoTag}>Auto-filled</div>}
      </div>
      <div style={{
        padding: '18px 20px',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px 20px',
      }}
      >
        {fields.map((f) => (
          <div key={`${f.group}.${f.name}`}>
            <label style={label} htmlFor={`${f.group}-${f.name}`}>{f.label}</label>
            <input
              id={`${f.group}-${f.name}`}
              type="text"
              value={f.value}
              onChange={(e) => onChange(f.group, f.name, e.target.value)}
              style={input}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function IdentityCards({ identity, editedGroups, onChange }: Props) {
  const s = identity.subscriber;
  const b = identity.billingProvider;
  const a = identity.attendingProvider;

  const subscriberFields: Field[] = [
    { group: 'subscriber', name: 'memberId', label: 'Member ID', value: s.memberId },
    { group: 'subscriber', name: 'last', label: 'Last Name', value: s.last },
    { group: 'subscriber', name: 'first', label: 'First Name', value: s.first },
    { group: 'subscriber', name: 'dob', label: 'Date of Birth (CCYYMMDD)', value: s.dob },
  ];

  const providerFields: Field[] = [
    { group: 'billingProvider', name: 'npi', label: 'Billing NPI', value: b.npi },
    { group: 'billingProvider', name: 'name', label: 'Billing Name', value: b.name },
  ];
  if (a) {
    providerFields.push(
      { group: 'attendingProvider', name: 'npi', label: 'Attending NPI', value: a.npi },
      { group: 'attendingProvider', name: 'last', label: 'Attending Last Name', value: a.last },
      { group: 'attendingProvider', name: 'first', label: 'Attending First Name', value: a.first },
    );
  }
  if (identity.taxId !== undefined) {
    providerFields.push(
      { group: 'taxId', name: 'taxId', label: 'Tax ID', value: identity.taxId },
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Card
        name="Subscriber / Member Info"
        groups={['subscriber']}
        fields={subscriberFields}
        editedGroups={editedGroups}
        onChange={onChange}
      />
      <Card
        name="Provider Info"
        groups={['billingProvider', 'attendingProvider', 'taxId']}
        fields={providerFields}
        editedGroups={editedGroups}
        onChange={onChange}
      />
    </div>
  );
}
