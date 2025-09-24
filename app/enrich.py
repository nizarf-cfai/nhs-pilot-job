import gcs_operation
import config
import time







class patientEnrich:
    def __init__(self, patient):
        self.patient = patient
        self.p_json_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}/{self.patient.get('patient_id')}.json"


    def add_status(self,process_obj):
        if not self.patient.get('status'):
            self.patient['status'] = []
        
        self.patient['status'].append(process_obj)

        gcs_operation.write_json_to_gcs(self.p_json_path, self.patient)
        return self.patient
    

    def enrich_ehr(self):
        bucket_path = self.patient.get('patient_bucket_path')
        if not self.patient.get('ehr_note'):
            self.patient['ehr_note'] = []

        files = gcs_operation.list_gcs_children(bucket_path + '/EHR')
        for f in files:
            if '.txt' in f:
                encounter_id = f.split('/')[-1].replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['ehr_note'].append(
                    {
                        "encounter_id" : encounter_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "EHR"
        })
        return self.patient
        

    def enrich_lab(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/LABS'
        if not self.patient.get('lab_result'):
            self.patient['lab_result'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['lab_result'].append(
                    {
                        "lab_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "LABS"
        })
        return self.patient
    
    def enrich_Nervecentre(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/Nervecentre'
        if not self.patient.get('nerve_center_data'):
            self.patient['nerve_center_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['nerve_center_data'].append(
                    {
                        "nerve_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "Nervecentre"
        })
        return self.patient
    
    def enrich_Medilogik(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/Medilogik'
        if not self.patient.get('medilogik_data'):
            self.patient['medilogik_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['medilogik_data'].append(
                    {
                        "medilogik_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "Medilogik"
        })
        return self.patient
    
    def enrich_Viper(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/Viper'
        if not self.patient.get('viper_data'):
            self.patient['viper_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['viper_data'].append(
                    {
                        "viper_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "Viper"
        })
        return self.patient
    
    def enrich_ICE(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/ICE'
        if not self.patient.get('ice_data'):
            self.patient['ice_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['ice_data'].append(
                    {
                        "ice_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "ICE"
        })
        return self.patient
    
    def enrich_BigHand(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/BigHand'
        if not self.patient.get('bighand_data'):
            self.patient['bighand_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['bighand_data'].append(
                    {
                        "bighand_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "BigHand"
        })
        return self.patient

    def enrich_VueExplore(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/VueExplore'
        if not self.patient.get('vue_data'):
            self.patient['vue_data'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['vue_data'].append(
                    {
                        "vue_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "VueExplore"
        })
        return self.patient
