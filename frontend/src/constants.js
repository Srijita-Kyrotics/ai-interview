import { FileText, Building2, Brain, Code2, MessageSquare, Users, BarChart2 } from 'lucide-react'

const steps = [
  { key: 'resume', label: 'Upload Resume', badge: '01', icon: FileText },
  { key: 'company', label: 'Targeted Companies', badge: '02', icon: Building2 },
  { key: 'aptitude', label: 'Aptitude', badge: '03', icon: Brain },
  { key: 'coding', label: 'Coding', badge: '04', icon: Code2 },
  { key: 'technical', label: 'Technical', badge: '05', icon: MessageSquare },
  { key: 'hr', label: 'HR Interview', badge: '06', icon: Users },
  { key: 'report', label: 'Report', badge: '07', icon: BarChart2 }
]

const roundDurations = {
  aptitude: 20,
  coding: 10 * 60
}

const interviewQuestionDuration = 5 * 60

const COMPANY_META = {
  // ── Product-Based ──────────────────────────────────────
  Google: {
    fullName: 'Google LLC',
    initials: 'G',
    logo: '/logo/google-logo.jpg',
    logoClass: 'logo-google',
    accent: '#eab308',
    bg: 'rgba(234,179,8,0.08)',
    type: 'product'
  },
  Microsoft: {
    fullName: 'Microsoft Corporation',
    initials: 'MS',
    logo: '/logo/microsoft-logo-4.png',
    logoClass: 'logo-microsoft',
    accent: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    type: 'product'
  },
  Amazon: {
    fullName: 'Amazon.com, Inc.',
    initials: 'AMZ',
    logo: '/logo/amazon logo.jpg',
    logoClass: 'logo-amazon',
    accent: '#ea580c',
    bg: 'rgba(249,115,22,0.08)',
    type: 'product'
  },
  Adobe: {
    fullName: 'Adobe Inc.',
    initials: 'ADB',
    logo: '/logo/Adobe-logo.png',
    logoClass: 'logo-adobe',
    accent: '#e13122',
    bg: 'rgba(225,49,34,0.08)',
    type: 'product'
  },
  Oracle: {
    fullName: 'Oracle Corporation',
    initials: 'ORC',
    logo: '/logo/oracle-logo.png',
    logoClass: 'logo-oracle',
    accent: '#c74634',
    bg: 'rgba(199,70,52,0.08)',
    type: 'product'
  },
  Salesforce: {
    fullName: 'Salesforce, Inc.',
    initials: 'SF',
    logo: '/logo/salesforce-logo.png',
    logoClass: 'logo-salesforce',
    accent: '#00a1e0',
    bg: 'rgba(0,161,224,0.08)',
    type: 'product'
  },
  Atlassian: {
    fullName: 'Atlassian Corporation',
    initials: 'ATL',
    logo: '/logo/Atlassian-Logo.jpg',
    logoClass: 'logo-atlassian',
    accent: '#0052cc',
    bg: 'rgba(0,82,204,0.08)',
    type: 'product'
  },
  NVIDIA: {
    fullName: 'NVIDIA Corporation',
    initials: 'NVD',
    logo: '/logo/nvidia-logo.png',
    logoClass: 'logo-nvidia',
    accent: '#76b900',
    bg: 'rgba(118,185,0,0.08)',
    type: 'product'
  },

  // ── Service-Based ───────────────────────────────────────
  TCS: {
    fullName: 'Tata Consultancy Services',
    initials: 'TCS',
    logo: '/logo/TCS-logo.jpg',
    logoClass: 'logo-tcs',
    accent: '#0369a1',
    bg: 'rgba(14,165,233,0.08)',
    type: 'service'
  },
  Infosys: {
    fullName: 'Infosys Limited',
    initials: 'INF',
    logo: '/logo/infosys-logo.jpg',
    logoClass: 'logo-infosys',
    accent: '#0f766e',
    bg: 'rgba(20,184,166,0.08)',
    type: 'service'
  },
  Wipro: {
    fullName: 'Wipro Limited',
    initials: 'WIP',
    logo: '/logo/wipro-logo.png',
    logoClass: 'logo-wipro',
    accent: '#1d4ed8',
    bg: 'rgba(59,130,246,0.08)',
    type: 'service'
  },
  HCLTech: {
    fullName: 'HCLTech',
    initials: 'HCL',
    logo: '/logo/hcl-tech.png',
    logoClass: 'logo-hcl',
    accent: '#00539b',
    bg: 'rgba(0,83,155,0.08)',
    type: 'service'
  },
  'Tech Mahindra': {
    fullName: 'Tech Mahindra Limited',
    initials: 'TM',
    logo: '/logo/tech-mahindra-logo.png',
    logoClass: 'logo-tech-mahindra',
    accent: '#e31937',
    bg: 'rgba(227,25,55,0.08)',
    type: 'service'
  },
  Cognizant: {
    fullName: 'Cognizant Technology Solutions',
    initials: 'CTS',
    logo: '/logo/cognizant-logo.jpg',
    logoClass: 'logo-cognizant',
    accent: '#334155',
    bg: 'rgba(148,163,184,0.08)',
    type: 'service'
  },
  Capgemini: {
    fullName: 'Capgemini',
    initials: 'CPG',
    logo: '/logo/capgemini-logo.jpg',
    logoClass: 'logo-capgemini',
    accent: '#0ea5e9',
    bg: 'rgba(14,165,233,0.08)',
    type: 'service'
  },
  LTIMindtree: {
    fullName: 'LTIMindtree Limited',
    initials: 'LTI',
    logo: '/logo/LTIMindtree_Logo.svg.png',
    logoClass: 'logo-ltimindtree',
    accent: '#6d28d9',
    bg: 'rgba(109,40,217,0.08)',
    type: 'service'
  },

  // ── Hybrid (Product + Service) ──────────────────────────
  Accenture: {
    fullName: 'Accenture',
    initials: 'ACN',
    logo: '/logo/accenture-logo.png',
    logoClass: 'logo-accenture',
    accent: '#7c3aed',
    bg: 'rgba(167,139,250,0.08)',
    type: 'both'
  },
  IBM: {
    fullName: 'IBM Corporation',
    initials: 'IBM',
    logo: '/logo/ibm-logo.png',
    logoClass: 'logo-ibm',
    accent: '#1f70c1',
    bg: 'rgba(31,112,193,0.08)',
    type: 'both'
  },
  SAP: {
    fullName: 'SAP SE',
    initials: 'SAP',
    logo: '/logo/SAP-Logo.svg.png',
    logoClass: 'logo-sap',
    accent: '#0070f2',
    bg: 'rgba(0,112,242,0.08)',
    type: 'both'
  },
  Cisco: {
    fullName: 'Cisco Systems, Inc.',
    initials: 'CSC',
    logo: '/logo/Cisco_logo_blue_2016.svg.png',
    logoClass: 'logo-cisco',
    accent: '#00bceb',
    bg: 'rgba(0,188,235,0.08)',
    type: 'both'
  },
  Zoho: {
    fullName: 'Zoho Corporation',
    initials: 'ZHO',
    logo: '/logo/ZOHO_logo_2023.svg.png',
    logoClass: 'logo-zoho',
    accent: '#e42527',
    bg: 'rgba(228,37,39,0.08)',
    type: 'both'
  },
  Freshworks: {
    fullName: 'Freshworks Inc.',
    initials: 'FW',
    logo: '/logo/freshworks-logo.png',
    logoClass: 'logo-freshworks',
    accent: '#22c55e',
    bg: 'rgba(34,197,94,0.08)',
    type: 'both'
  }
}

const COMPANY_GROUPS = [
  {
    key: 'product',
    badge: 'Product-Based',
    sub: 'Build and own world-class software products',
    companies: ['Google', 'Microsoft', 'Amazon', 'Adobe', 'Oracle', 'Salesforce', 'Atlassian', 'NVIDIA']
  },
  {
    key: 'service',
    badge: 'Service-Based',
    sub: 'Large IT services and consulting firms',
    companies: ['TCS', 'Infosys', 'Wipro', 'HCLTech', 'Tech Mahindra', 'Cognizant', 'Capgemini', 'LTIMindtree']
  },
  {
    key: 'hybrid',
    badge: 'Hybrid',
    sub: 'Companies with both product and service-led hiring tracks',
    companies: ['Accenture', 'IBM', 'SAP', 'Cisco', 'Zoho', 'Freshworks']
  }
]

const ROLE_MAPPINGS = {
  'Frontend Developer': {
    keywords: ['react', 'vue', 'angular', 'html', 'css', 'javascript', 'tailwind', 'bootstrap', 'next', 'frontend'],
    difficulty: 'medium',
    techStack: ['React', 'TypeScript', 'CSS', 'Webpack', 'REST APIs']
  },
  'Backend Developer': {
    keywords: ['node', 'express', 'python', 'django', 'java', 'spring', 'sql', 'mongodb', 'backend', 'api'],
    difficulty: 'medium',
    techStack: ['Node.js', 'SQL', 'REST APIs', 'Docker', 'Redis']
  },
  'Full Stack Developer': {
    keywords: ['react', 'node', 'mongodb', 'express', 'javascript', 'python', 'django', 'full stack'],
    difficulty: 'hard',
    techStack: ['React', 'Node.js', 'MongoDB', 'Express', 'GraphQL']
  },
  'Machine Learning Engineer': {
    keywords: ['python', 'tensorflow', 'pytorch', 'scikit', 'ml', 'data science', 'keras', 'machine learning'],
    difficulty: 'hard',
    techStack: ['Python', 'TensorFlow', 'PyTorch', 'Pandas', 'scikit-learn']
  },
  'Data Analyst': {
    keywords: ['sql', 'excel', 'power bi', 'tableau', 'python', 'r', 'data analysis', 'pandas'],
    difficulty: 'easy',
    techStack: ['SQL', 'Power BI', 'Tableau', 'Python', 'Excel']
  },
  'DevOps Engineer': {
    keywords: ['docker', 'kubernetes', 'aws', 'ci/cd', 'jenkins', 'linux', 'cloud', 'devops'],
    difficulty: 'hard',
    techStack: ['Docker', 'Kubernetes', 'AWS', 'Terraform', 'Jenkins']
  },
  'AI Engineer': {
    keywords: ['llm', 'openai', 'langchain', 'nlp', 'transformers', 'huggingface', 'ai', 'prompt'],
    difficulty: 'hard',
    techStack: ['LangChain', 'OpenAI API', 'HuggingFace', 'Python', 'Vector DBs']
  },
  'Cloud Engineer': {
    keywords: ['aws', 'azure', 'gcp', 'cloud', 'lambda', 's3', 'terraform', 'serverless'],
    difficulty: 'medium',
    techStack: ['AWS', 'Terraform', 'Kubernetes', 'Azure', 'GCP']
  }
}

export { steps, roundDurations, interviewQuestionDuration, COMPANY_META, COMPANY_GROUPS, ROLE_MAPPINGS }
