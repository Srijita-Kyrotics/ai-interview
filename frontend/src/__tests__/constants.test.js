import { describe, it, expect } from 'vitest'
import { steps, COMPANY_META, COMPANY_GROUPS, ROLE_MAPPINGS } from '../constants'

describe('steps', () => {
  it('has 7 steps', () => {
    expect(steps).toHaveLength(7)
  })

  it('first step is resume', () => {
    expect(steps[0].key).toBe('resume')
  })

  it('last step is report', () => {
    expect(steps[steps.length - 1].key).toBe('report')
  })

  it('each step has required fields', () => {
    steps.forEach(step => {
      expect(step).toHaveProperty('key')
      expect(step).toHaveProperty('label')
      expect(step).toHaveProperty('badge')
    })
  })
})

describe('COMPANY_META', () => {
  it('contains Google', () => {
    expect(COMPANY_META.Google).toBeDefined()
    expect(COMPANY_META.Google.fullName).toBe('Google LLC')
  })

  it('contains Microsoft', () => {
    expect(COMPANY_META.Microsoft).toBeDefined()
  })

  it('each company has required fields', () => {
    Object.values(COMPANY_META).forEach(company => {
      expect(company).toHaveProperty('fullName')
      expect(company).toHaveProperty('initials')
      expect(company).toHaveProperty('accent')
      expect(company).toHaveProperty('type')
    })
  })

  it('has product and service types', () => {
    const types = new Set(Object.values(COMPANY_META).map(c => c.type))
    expect(types.has('product')).toBe(true)
    expect(types.has('service')).toBe(true)
  })
})

describe('COMPANY_GROUPS', () => {
  it('is an array of groups', () => {
    expect(Array.isArray(COMPANY_GROUPS)).toBe(true)
    expect(COMPANY_GROUPS.length).toBeGreaterThan(0)
  })

  it('each group has key, badge, and companies array', () => {
    COMPANY_GROUPS.forEach(group => {
      expect(group).toHaveProperty('key')
      expect(group).toHaveProperty('badge')
      expect(group).toHaveProperty('companies')
      expect(Array.isArray(group.companies)).toBe(true)
    })
  })
})

describe('ROLE_MAPPINGS', () => {
  it('has role mappings', () => {
    expect(Object.keys(ROLE_MAPPINGS).length).toBeGreaterThan(0)
  })

  it('each mapping has keywords and techStack', () => {
    Object.values(ROLE_MAPPINGS).forEach(mapping => {
      expect(mapping).toHaveProperty('keywords')
      expect(mapping).toHaveProperty('techStack')
      expect(Array.isArray(mapping.keywords)).toBe(true)
      expect(Array.isArray(mapping.techStack)).toBe(true)
    })
  })
})
