/**
 * Módulo de Dados Expandido - PrevEvasão
 */

const CAMPUS_DATA = [
    { id: "central", name: "Câmpus Central", icon: "fa-building-columns", location: "Sede Principal", total: 12450, alerta: 312, critico: 84, chance: 8.4 },
    { id: "inovacao", name: "Câmpus Inovação", icon: "fa-flask", location: "Polo Tecnológico", total: 4120, alerta: 95, critico: 18, chance: 4.3 },
    { id: "saude", name: "Câmpus Ciências da Saúde", icon: "fa-heart-pulse", location: "Polo Hospitalar", total: 3890, alerta: 114, critico: 32, chance: 5.9 }
];

const COURSES_DATA = {
    "Câmpus Central": [
        { name: "Ciência da Computação", code: "CC-01", total: 150, alerta: 12, critico: 4, chance: 10.5 },
        { name: "Engenharia Civil", code: "EC-02", total: 240, alerta: 18, critico: 3, chance: 6.2 },
        { name: "Administração", code: "ADM-03", total: 310, alerta: 22, critico: 7, chance: 7.8 }
    ],
    "Câmpus Inovação": [
        { name: "Análise e Desenvolvimento de Sistemas", code: "ADS-01", total: 180, alerta: 15, critico: 2, chance: 5.4 },
        { name: "Sistemas de Informação", code: "SI-02", total: 200, alerta: 10, critico: 1, chance: 3.2 }
    ],
    "Câmpus Ciências da Saúde": [
        { name: "Medicina", code: "MED-01", total: 400, alerta: 5, critico: 1, chance: 1.5 },
        { name: "Enfermagem", code: "ENF-02", total: 280, alerta: 24, critico: 8, chance: 9.1 }
    ]
};

const STUDENTS_DATA = {
    "Ciência da Computação": [
        { nome: "Ana Silva Medeiros", mat: "2024018842", econ: "Crítico (Baixa Renda)", econStatus: "danger", psici: "Crítico (SRQ-20 Elevado)", psiciStatus: "danger", sigaa: "Sem acessos há 15 dias", sigaaStatus: "danger", chance: 94 },
        { nome: "Carlos Eduardo Costa", mat: "2023029115", econ: "Moderado (Auxílio Solicitado)", econStatus: "warning", psici: "Crítico (Sintomas Graves)", psiciStatus: "danger", sigaa: "Acessos reduzidos (-60%)", sigaaStatus: "warning", chance: 82 },
        { nome: "Gabriel Almeida Melo", mat: "2025019940", econ: "Estável", econStatus: "success", psici: "Estável", psiciStatus: "success", sigaa: "Frequente e Ativo", sigaaStatus: "success", chance: 12 }
    ],
    "Engenharia Civil": [
        { nome: "Bruno Rocha Oliveira", mat: "2022041102", econ: "Crítico (Perda de Vínculo)", econStatus: "danger", psici: "Estável", psiciStatus: "success", sigaa: "Acessos normais", sigaaStatus: "success", chance: 54 },
        { nome: "Beatriz Lima Ferreira", mat: "2024021109", econ: "Estável", econStatus: "success", psici: "Moderado (Acompanhamento)", psiciStatus: "warning", sigaa: "Acessos reduzidos (-35%)", sigaaStatus: "warning", chance: 38 }
    ],
    "Análise e Desenvolvimento de Sistemas": [
        { nome: "Lucas Martins Rocha", mat: "2023055120", econ: "Crítico (Insegurança)", econStatus: "danger", psici: "Moderado", psiciStatus: "warning", sigaa: "Sem acessos há 12 dias", sigaaStatus: "danger", chance: 88 },
        { nome: "Amanda Vieira Dias", mat: "2024099412", econ: "Estável", econStatus: "success", psici: "Estável", psiciStatus: "success", sigaa: "Acessos reduzidos (-40%)", sigaaStatus: "warning", chance: 29 }
    ],
    "Enfermagem": [
        { nome: "Juliana Mendes Frota", mat: "2022031120", econ: "Moderado", econStatus: "warning", psici: "Crítico (Ansiedade SRQ)", psiciStatus: "danger", sigaa: "Sem acessos há 20 dias", sigaaStatus: "danger", chance: 91 },
        { nome: "Pedro Henrique Justo", mat: "2023019855", econ: "Crítico (Vulnerável)", econStatus: "danger", psici: "Moderado", psiciStatus: "warning", sigaa: "Acessos normais", sigaaStatus: "success", chance: 62 }
    ]
};