import json
import itertools
from tqdm import tqdm
import pandas as pd
import asyncio
from custom_runners import CRunner
import agent_list
import config
import gcs_operation


class PairwisePatient:
    def __init__(self, process_id):
        self.process_id = process_id


    def get_patient_obj_list(self):
        patient_list_path = gcs_operation.list_gcs_children(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patients")

        result = []

        for p_path in patient_list_path[:3]:
            p_json_path = p_path + f"{p_path.split('/')[-2]}.json"
            print("patient json path :", p_json_path)

            p_data = gcs_operation.read_json_from_gcs(p_json_path)
            result.append(p_data)
        return result

    def load_patient_data(self, patient_list_obj):
        compare_items = []
        for p in patient_list_obj:
            # Concatenate relevant fields (you can adjust depending on your schema)
            patient_str = ""
            patient_str += f"Risk level : {p.get('debate_category',{}).get('risk')}\n"
            patient_str += f"Reason : {p.get('debate_category',{}).get('resoning')}\n"
            patient_str += f"Evidence : {p.get('debate_category',{}).get('evidence')}\n"
                
            compare_items.append({
                'patient_id': p.get('patient_id'),
                'result': patient_str
            })
            
        return compare_items

    async def compare_patients(self, patient1, patient2):
        """Compare two patients and decide which one is in more critical condition"""
        prompt = f"""Compare these 2 patients and decide which has the more critical condition. 
    Base your decision on severity of symptoms, diagnosis, risk factors, and lab results.
    Return only 'A' if Patient A is more critical, 'B' if Patient B is more critical, 
    or 'Equal' if both are equally critical.

    Patient A: {patient1['patient_id']}
    Details:
    {patient1['result']}

    Patient B: {patient2['patient_id']}
    Details:
    {patient2['result']}
    """
        res_obj = CRunner(
            agent=agent_list.pairwise_agent,
            prompt=prompt,
            format_output=agent_list.Pairwise
        )
        await res_obj.run_async()
        
        return res_obj.output['winner']  # 'A', 'B', or 'Equal'

    def calculate_win_rates(self, comparison_results):
        """Calculate how often each patient was more critical"""
        win_counts = {}
        total_matches = {}
        
        for (p1, p2), winner in comparison_results.items():
            if winner not in ['A', 'B']:
                continue
                
            for patient in [p1, p2]:
                if patient not in win_counts:
                    win_counts[patient] = 0
                    total_matches[patient] = 0
            
            if winner == 'A':
                win_counts[p1] += 1
            elif winner == 'B':
                win_counts[p2] += 1
                
            total_matches[p1] += 1
            total_matches[p2] += 1
        
        win_rates = {}
        for patient in win_counts:
            win_rate = (win_counts[patient] / total_matches[patient]) * 100 if total_matches[patient] > 0 else 0
            win_rates[patient] = {
                'criticality_rate': round(win_rate, 2),
                'critical_votes': win_counts[patient],
                'total_matches': total_matches[patient]
            }
        
        return win_rates

    async def run_comparisons(self, pairs, client):
        comparison_results = {}
        for p1, p2 in tqdm(pairs, desc="Comparing patients"):
            result = await self.compare_patients(p1, p2, client)
            if result:
                comparison_results[(p1['patient_id'], p2['patient_id'])] = result
        return comparison_results

    async def main(self):
        # Load patient data
        patient_obj_list = self.get_patient_obj_list()

        high_med = {
            'high' : [],
            "medium" : []
        }
        for p in patient_obj_list:
            if 'high' in p.get('debate_category',{}).get('risk','').lower():
                high_med['high'].append(p)
            elif 'medium' in p.get('debate_category',{}).get('risk','').lower():
                high_med['medium'].append(p)

        for level, obj_list in high_med.items():
            data = self.load_patient_data(obj_list)
            
            print(f"\nLoaded {len(data)} patients for comparison")
            if data:
                print("Sample data format:")
                print(json.dumps(data[0], indent=2))
            
            # Generate all patient pairs
            pairs = list(itertools.combinations(data, 2))
            print(f"\nWill perform {len(pairs)} pairwise comparisons")
            
            # Run comparisons
            comparison_results = await self.run_comparisons(pairs, None)
            
            # Calculate ranking
            win_rates = self.calculate_win_rates(comparison_results)
            
            df = pd.DataFrame([
                {
                    'Patient': patient,
                    'Criticality Rate (%)': stats['criticality_rate'],
                    'Critical Votes': stats['critical_votes'],
                    'Total Matches': stats['total_matches']
                }
                for patient, stats in win_rates.items()
            ])
            
            df = df.sort_values('Criticality Rate (%)', ascending=False)

            records = df.to_dict(orient="records")


