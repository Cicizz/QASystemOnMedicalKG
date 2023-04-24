#!/usr/bin/env python3
# coding: utf-8
# File: answer_search.py
# Author: lhy<lhy_in_blcu@126.com,https://huangyong.github.io>
# Date: 18-10-5

from collections import Counter

from py2neo import Graph

from question_parser import QuestionPaser


class AnswerSearcher:

    def __init__(self):
        # self.g = Graph(
        #     host="localhost",
        #     http_port=7474,
        #     user="",
        #     password="")
        self.g = Graph("http://localhost:7474", user="medical", password="medical")
        self.num_limit = 20
        self.parser = QuestionPaser()

    '''执行cypher查询，并返回相应结果'''

    def search_main(self, ner_word, history_match_diseases,history_match_dep):
        types = ner_word.keys()

        # 1. 若科室是一级科室，则反问更细科室的症状，从而推荐二级科室,一级科室包括：妇产科，外科，内科，五官科，皮肤性病科
        if 'department' in types:
            dep_arr = ner_word['department']
            return self.search_and_recommend_dep(dep_arr,history_match_dep)


        # 2. 若是疾病，则查询疾病关联的科室并进行推荐
        if 'disease' in types:
            sql = self.parser.sql_transfer('disease_department', ner_word['disease'])
            recommend_deps = self.search_graph(sqls=sql, return_key='n.name')
            return self.search_and_recommend_dep(recommend_deps, history_match_dep)

        # 3.若是命中其他实体，搜索命中的疾病数
        if 'check' in types:
            sql = self.parser.sql_transfer('check_disease', ner_word['check'])
        elif 'symptom' in types:
            sql = self.parser.sql_transfer('symptom_disease', ner_word['symptom'])
        else:
            return '未识别'
        diseases = self.search_graph(sqls=sql, return_key='m.name')

        # 3.1 判断历史是否有一些疾病，若再次命中说明匹配度很高，直接使用
        high_match_disease = []
        for disease in diseases:
            if disease in history_match_diseases:
                high_match_disease.append(disease)

        if len(high_match_disease) > 0:
            sql = self.parser.sql_transfer('disease_department', high_match_disease)
            recommend_departments = self.search_graph(sql)
            return self.search_and_recommend_dep(recommend_departments, history_match_dep)
        elif len(diseases) <= 3:
            sql = self.parser.sql_transfer('disease_department', diseases)
            recommend_departments = self.search_graph(sql)
            return self.search_and_recommend_dep(recommend_departments, history_match_dep)
        else:
            # 获取疾病的三个关联症状
            history_match_diseases.extend(diseases)
            diseases = self.cal_high_odds_disease(diseases)
            sql = self.parser.sql_transfer('disease_symptom', diseases)
            symptoms = self.search_graph(sqls=sql, return_key='n.name')
            return self.answer_prettify('ask_symptom', symptoms)

    def cal_high_odds_disease(self,diseases):
        dis_cnt = Counter(diseases)
        sorted_x = sorted(dis_cnt.items(), key=lambda x: x[1], reverse=True)
        sorted_x = dict(sorted_x)
        return sorted_x.keys()


    def search_and_recommend_dep(self,dep_arr,history_match_dep):
        rec_deps = []
        has_child_deps = []
        for dep in dep_arr:
            # 1.1 二级科室,匹配的，放进来，说明推荐优先级高
            if self.parser.is_first_department(dep) is not True:
                rec_deps.append(dep)
            else:
                has_child_deps.append(dep)
        if len(rec_deps) > 0:
            rec_deps = self.high_match_department(rec_deps,history_match_dep)
            return self.answer_prettify('recommend_department', rec_deps)
        else:
            # 查询子科室，定优先级
            sql = self.parser.sql_transfer('department_child', has_child_deps)
            child_deps = self.search_graph(sqls=sql, return_key='m.name')
            history_match_dep.extend(child_deps)

            # 查询子科室下的症状
            sql = self.parser.sql_transfer('department_child_symptom', has_child_deps)
            child_symptoms = self.search_graph(sqls=sql, return_key='m.name')
            return self.answer_prettify('ask_symptom', child_symptoms)

    def search_graph(self, sqls, return_key='m.name'):
        answers = []
        for sql in sqls:
            search_answer = self.g.run(sql).data()
            for answer in search_answer:
                answers.append(answer[return_key])
        return answers

    '''根据对应的qustion_type，调用相应的回复模板'''
    def answer_prettify(self, question_type, answers):
        final_answer = []
        if not answers:
            return ''
        if question_type == 'recommend_department':
            final_answer = '推荐您到以下科室挂科:{0}'.format('；'.join(list(set(answers))[:self.num_limit]))

        elif question_type == 'ask_symptom':  # 反问症状
            final_answer = '请问您还有以下症状吗（请选择一个或多个）：{0}'.format('；'.join(list(set(answers))[:self.num_limit]))

        return final_answer

    def high_match_department(self,search_deps,history_deps):
        recommed_deps = []
        if len(history_deps) == 0:
            return search_deps

        if len(search_deps) == 0 and len(history_deps) != 0:
            return history_deps if len(history_deps) < 3 else history_deps[0:3]

        for sdep in search_deps:
            for history_dep in history_deps:
                if sdep == history_dep:
                    recommed_deps.append(sdep)
        if len(recommed_deps) > 0:
            return recommed_deps
        return search_deps

if __name__ == '__main__':
    searcher = AnswerSearcher()
